from typing import Any

from sekaibot import Bot, Node
from sekaibot.adapter.cqhttp.event import MessageEvent
from sekaibot.dependencies import Depends
from sekaibot.rule import ToMe

@ToMe()
class NormalMsg(Node[MessageEvent, dict, Any]):
    priority: int = 2
    block: bool = False

    async def handle(self) -> None:
        if "/clear" in self.event.get_plain_text():
            await self.response._clear_chat_memory_tool(None)
            return
        await self.response.respond_to_message(if_music=True, if_img=False)

    async def rule(self) -> bool:
        print(self.event.is_tome())
        if "请使用最新版本" in self.event.get_plain_text():
            return False
        if self.event.user_id == 2854196310:
            return False
        return True
