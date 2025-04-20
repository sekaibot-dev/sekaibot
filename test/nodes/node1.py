from typing_extensions import override

from sekaibot import Node


class Node1(Node):
    priority = 0

    @override
    async def handle(self) -> None:
        await self.event.adapter.call_api("fake", fake="fake")

    @override
    async def rule(self) -> bool:
        return True
