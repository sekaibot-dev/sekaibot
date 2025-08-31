"""# from typing import Any"""

import re
import warnings
from datetime import datetime
from typing import Any, Literal, TypedDict
from typing_extensions import override
from zoneinfo import ZoneInfo

from anyio import sleep
from cogniweave import build_pipeline, init_config
from langchain_core.runnables.base import Runnable

from sekaibot import Node
from sekaibot.adapter.cqhttp.event import PrivateMessageEvent

warnings.filterwarnings("ignore")


class SegmentDelay(TypedDict):
    """返回列表中每个元素的类型定义。"""

    output: str
    delay: float


def split_with_delay(
    input: str,  # noqa: A002
    *,
    coefficient: float = 0.2,
) -> list[SegmentDelay]:
    """将输入数据中的 `output` 字段按空格拆分，并为每个子串添加延迟。"""
    if not input or not isinstance(input, str):
        return []
    raw = input.strip()
    if not raw:
        return []

    segments = re.split(r"\s+", raw)

    result: list[SegmentDelay] = []
    for i, segment in enumerate(segments):
        delay = 0.0 if i == 0 else len(segment) * coefficient
        result.append({"output": segment, "delay": delay})

    return result


_RUNNABLE_KEY: Literal["_runnable"] = "_runnable"
_OPTIONAL_PROMPT_KEY: Literal["_optional_prompt"] = "_optional_prompt"
_RESULT_WARNING_COUNT_KEY: Literal["_result_warning_count"] = "_result_warning_count"


class PrivateReply(Node[PrivateMessageEvent, dict, Any]):  # type: ignore
    priority = 1

    def get_or_create_runnable(self) -> Runnable:
        if _RUNNABLE_KEY not in self.node_state:
            init_config(_config_file="./example/chat_config.toml")
            self.node_state[_RUNNABLE_KEY] = build_pipeline() | split_with_delay
        return self.node_state[_RUNNABLE_KEY]

    @property
    def optional_prompt(self) -> str:
        if _OPTIONAL_PROMPT_KEY not in self.node_state:
            self.node_state[_OPTIONAL_PROMPT_KEY] = {}
        if self.event.get_session_id() not in self.node_state[_OPTIONAL_PROMPT_KEY]:
            self.node_state[_OPTIONAL_PROMPT_KEY][self.event.get_session_id()] = ""
        return self.node_state[_OPTIONAL_PROMPT_KEY][self.event.get_session_id()]

    @optional_prompt.setter
    def optional_prompt(self, value: str) -> None:
        if _OPTIONAL_PROMPT_KEY not in self.node_state:
            self.node_state[_OPTIONAL_PROMPT_KEY] = {}
        self.node_state[_OPTIONAL_PROMPT_KEY][self.event.get_session_id()] = value

    @property
    def result_warning_count(self) -> int:
        if _RESULT_WARNING_COUNT_KEY not in self.node_state:
            self.node_state[_RESULT_WARNING_COUNT_KEY] = {}
        if (
            self.event.get_session_id()
            not in self.node_state[_RESULT_WARNING_COUNT_KEY]
        ):
            self.node_state[_RESULT_WARNING_COUNT_KEY][self.event.get_session_id()] = 0
        return self.node_state[_RESULT_WARNING_COUNT_KEY][self.event.get_session_id()]

    @result_warning_count.setter
    def result_warning_count(self, value: int) -> None:
        if _RESULT_WARNING_COUNT_KEY not in self.node_state:
            self.node_state[_RESULT_WARNING_COUNT_KEY] = {}
        self.node_state[_RESULT_WARNING_COUNT_KEY][self.event.get_session_id()] = value

    @override
    async def handle(self) -> None:
        runnable = self.get_or_create_runnable()
        text = self.event.get_plain_text()
        print(text)
        session_id = self.event.get_session_id()
        if not text:
            return

        keyws = ["clear", "清除", "清空", "清理", "删除", "重置", "重新开始", "重启"]
        if any(keyw in text for keyw in keyws):
            await runnable.ainvoke(
                {"action": "clear_history"},
                config={"configurable": {"session_id": session_id}},
            )
            self.optional_prompt = ""
            self.result_warning_count = 0
            await self.reply("已清除历史记录。")
            return

        if self.result_warning_count > 2:  # noqa: PLR2004
            await runnable.ainvoke(
                {"action": "clear_history"},
                config={"configurable": {"session_id": session_id}},
            )

        result = await runnable.ainvoke(
            {
                "input": text,
                "time": datetime.now(tz=ZoneInfo("Asia/Shanghai")).strftime(
                    "%Y年%m月%d日 %H时%M分"
                ),
                "optional_prompt": self.optional_prompt,
            },
            config={"configurable": {"session_id": session_id}},
        )

        if len(result) > 5 and len(result) != 0:  # noqa: PLR2004
            self.optional_prompt = (
                "### 【强制执行通知】\n\n"
                "- **强制执行通知：您的回复内容已超过五条分句。请立即严格按照要求，在下一条消息中缩短回复。**\n"
                "- **请务必重视：如未在下条消息中完成内容缩减，系统将立即终止本次对话，并永久清除所有历史内容，不可恢复。**\n"
                "- **本要求无任何例外。请确保严格遵守，否则后果自负。**\n"
            )
            self.result_warning_count += 1
        else:
            self.optional_prompt = ""
            self.result_warning_count = 0

        print(result, self.optional_prompt, self.result_warning_count)
        for segment in result:
            await sleep(segment["delay"])
            await self.reply(segment["output"])
