from typing_extensions import override

from sekaibot import Node


class Node2(Node):
    priority = 1

    @override
    async def handle(self) -> None:
        pass

    @override
    async def rule(self) -> bool:
        return True
