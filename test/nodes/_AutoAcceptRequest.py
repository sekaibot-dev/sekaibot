from sekaibot import Node


class AutoAcceptFriendRequest(Node):
    priority: int = 3
    block: bool = True

    async def handle(self) -> None:
        await self.comm.approve()

    async def rule(self) -> bool:
        if self.comm.adapter.name != "cqhttp":
            return False
        if self.info.type != "request":
            return False
        if self.info.request_type in ["friend", "group"]:
            return False
        return True
