"""MainChat节点"""

from typing import Any  # type: ignore

from sekaibot import Node
from sekaibot.adapter.cqhttp.event import GroupMessageEvent  # type: ignore

from .agent import clear
from .llm import get_answer, handle_img


# @WordFilter(word_file=Path("./example/nodes/sensitive_words_lines.txt"), use_aho=True)  # type: ignore
class MainChat(Node[GroupMessageEvent, dict, Any]):  # type: ignore
    """AIChat"""

    priority: int = 1

    async def handle(self) -> None:
        random_trigger = (
            "group_834922207" in self.event.get_session_id()
            or "group_788499440" in self.event.get_session_id()
            or "group_834922207" in self.event.get_session_id()
            or "group_895484096" in self.event.get_session_id()
        ) and self.event.get_user_id() != "1852262922"
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

        for msg in self.event.message:
            if msg.type == "image":
                img_url: str = msg.data.get("url")
                file_id: str = msg.data.get("file")
                if img_url and file_id:
                    await handle_img(
                        session_id=str(self.event.group_id),
                        name=name,
                        img_url=img_url,
                        file_id=file_id,
                    )
                return

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
        )
