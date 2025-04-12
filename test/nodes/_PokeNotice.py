from typing import Any

from sekaibot import Node
from sekaibot.adapters.cqhttp.event import PokeNotifyEvent


class PokeNotice(Node[PokeNotifyEvent, Any, Any]):
    priority: int = 2
    block: bool = False

    async def handle(self) -> None:
        if getattr(self.info, "group_id", None) is not None:
            await self.call_api(
                "group_poke", group_id=self.info.group_id, user_id=self.info.user_id
            )
        else:
            await self.call_api("friend_poke", user_id=self.info.user_id)

    async def rule(self) -> bool:
        return (
            self.event.target_id == self.event.self_id and self.event.user_id != self.event.self_id
        )
