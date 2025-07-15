"""# from typing import Any"""

import re
import warnings
from datetime import datetime
from typing import Annotated, Any, TypedDict
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


class PrivateReply(Node[PrivateMessageEvent, Annotated[Runnable, None], Any]):  # type: ignore
    priority = 1

    @override
    async def handle(self) -> None:
        if self.node_state is None:
            init_config(_config_file="./example/chat_config.toml")
            self.node_state = build_pipeline() | split_with_delay
        text = self.event.get_plain_text()
        print(text)
        session_id = self.event.get_session_id()
        if not text:
            return
        result = await self.node_state.ainvoke(
            {
                "input": text,
                "time": datetime.now(tz=ZoneInfo("Asia/Shanghai")).strftime(
                    "%Y年%m月%d日 %H时%M分"
                ),
            },
            config={"configurable": {"session_id": session_id}},
        )
        print(result)
        for segment in result:
            await sleep(segment["delay"])
            await self.reply(segment["output"])
