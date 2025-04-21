from pathlib import Path
from typing import Any

from sekaibot import Node
from sekaibot.adapter.cqhttp.event import GroupMessageEvent
from sekaibot.permission import SuperUser, User
from sekaibot.rule import WordFilter

from .llm import clear, get_answer


@WordFilter(word_file=Path("./example/nodes/sensitive_words_lines.txt"), use_aho=True)
@SuperUser()
@User("group_834922207", "group_788499440")
class AIChat(Node[GroupMessageEvent, dict, Any]):  # noqa: D101
    priority: int = 1
    block: bool = False

    async def handle(self) -> None:
        """处理"""
        if "/clear" in self.event.message:
            await clear(str(self.event.group_id))
            return
        img_url = None
        for msg in self.event.message:
            if msg.type == "image":
                img_url = msg.data.get("url")
                break
        if img_url:
            if answer := await get_answer(
                str(self.event.group_id), self.event.sender.nickname, img_url, True
            ):
                await self.reply(answer)
                self.stop()
        elif self.event.get_plain_text() and (
            answer := await get_answer(
                str(self.event.group_id),
                self.event.sender.nickname,
                self.event.get_plain_text(),
                False,
                self.event.is_tome(),
            )
        ):
            await self.reply(answer)
            self.stop()

    async def rule(self) -> bool:  # noqa: D102
        return (
            "请使用最新版本" not in self.event.get_plain_text()
            and self.event.user_id != 2854196310  # noqa: PLR2004
        )
