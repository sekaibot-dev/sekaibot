"""MainChat节点"""

from typing import Any

from sekaibot import Node
from sekaibot.adapter.cqhttp.event import GroupMessageEvent
from sekaibot.adapter.cqhttp.exceptions import ApiTimeout

from .agent import clear
from .llm import get_answer, handle_img


class MainChat(Node[GroupMessageEvent, dict, Any]):
    """AIChat"""

    priority: int = 0

    async def handle(self) -> None:
        random_trigger = "group_596488203" in self.event.get_session_id()
        """处理"""
        if "/clear" in self.event.message:
            await clear(str(self.event.group_id))
            return

        name_map: dict[str, str] = {
            "shiroko": "白子小姐",
            "空想少女": "アルス",
            "かたちなきもの": "言霊",
        }
        name: str = self.event.sender.nickname
        name = name_map.get(name, name)

        async def get_img_path(_file: str) -> str | None:
            try:
                return (await self.call_api("get_image", file=_file)).get("file", None)
            except ApiTimeout:
                return None

        for msg in self.event.message:
            if msg.type == "image":
                file: str = msg.data.get("file")
                await handle_img(
                    session_id=str(self.event.group_id),
                    name=name,
                    get_img_func=get_img_path,
                    file_id=file,
                )

        if self.event.get_plain_text() and (
            answer := await get_answer(
                session_id=str(self.event.group_id),
                name=name,
                message=self.event.get_plain_text(),
                is_tome=self.event.is_tome(),
                random_trigger=random_trigger,
            )
        ):
            await self.reply(answer)
            self.stop()

    async def rule(self) -> bool:
        return (
            "请使用最新版本" not in self.event.get_plain_text()
            and self.event.user_id != 2854196310  # noqa: PLR2004
            and self.event.get_user_id() != "1852262922"
            and self.event.get_user_id() != "303789917"
        )
