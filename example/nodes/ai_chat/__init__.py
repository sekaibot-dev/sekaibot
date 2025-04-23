"""MainChat节点"""

from typing import Any  # type: ignore

from apscheduler.triggers.cron import CronTrigger

from sekaibot import Node
from sekaibot.adapter.cqhttp.event import GroupMessageEvent  # type: ignore
from sekaibot.permission import SuperUser
from sekaibot.plugins.apscheduler import APSchedulerArg

from .llm import clear, get_answer, reset


# @WordFilter(word_file=Path("./example/nodes/sensitive_words_lines.txt"), use_aho=True)  # type: ignore
class MainChat(Node[GroupMessageEvent, dict, Any]):  # type: ignore
    """AIChat"""

    priority: int = 1
    scheduler = APSchedulerArg()

    async def handle(self) -> None:
        """处理"""
        job_id = "reset_count_daily"
        if not self.scheduler.get_job(job_id):  # ✅ 防止重复添加
            self.scheduler.add_job(reset, CronTrigger(hour=0, minute=0), id=job_id)
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
                session_id=str(self.event.group_id),
                name=self.event.sender.nickname,
                message=img_url,
                is_url=True,
            ):
                await self.reply(answer)
                self.stop()
        elif self.event.get_plain_text() and (
            answer := await get_answer(
                session_id=str(self.event.group_id),
                name=self.event.sender.nickname,
                message=self.event.get_plain_text(),
                is_url=False,
                is_tome=self.event.is_tome(),
            )
        ):
            await self.reply(answer)
            self.stop()

    async def rule(self) -> bool:  # noqa: D102
        return (
            "请使用最新版本" not in self.event.get_plain_text()
            and self.event.user_id != 2854196310  # noqa: PLR2004
            and (
                "group_834922207" in self.event.get_session_id()
                or "group_788499440" in self.event.get_session_id()
                or "group_834922207" in self.event.get_session_id()
                or "group_895484096" in self.event.get_session_id()
                or self.event.is_tome()
            )
        )
