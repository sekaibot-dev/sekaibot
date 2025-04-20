from typing import Any

from sekaibot import Node
from sekaibot.adapter.cqhttp.event import FriendRequestEvent, GroupRequestEvent


class AutoAcceptRequest(Node[FriendRequestEvent | GroupRequestEvent, Any, Any]):
    priority: int = 0
    block: bool = True

    async def handle(self) -> None:
        await self.event.approve()
