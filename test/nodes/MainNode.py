from typing import Any

from sekaibot import Depends, Event, Node, SonNode


# from sekaibot.rule import rule_at_me
class BEvent(Event):
    type: str = "a_event"
    adapter: str = "test_adapter"


class BNode(SonNode[Event, Any, Any]):
    def main(self):
        print(self.event.get_event_name())


class HelloWorldNode(Node[Event, Any, Any]):
    # if_startswith = StartsWith.Checker("Hello, World", True)
    # param = StartsWith.Param()

    """Hello, World! 示例节点。"""

    B: BNode = Depends()

    priority = 0

    async def handle(self):
        print("HelloWorldNode")
        self.B.main()
        return None


class HelloWorldNode1(Node):
    """Hello, World! 示例节点。"""

    parent = "HelloWorldNode"
    priority = 5

    async def handle(self):
        # print(self.bot.config.model_dump_json(indent=4))
        return None

    async def rule(self):
        # result = await self.run(StartsWith._rule_check("Hello, World"))
        return True


class HelloWorldNode2(Node):
    """Hello, World! 示例节点。"""

    parent = "HelloWorldNode"
    priority = 2

    async def handle(self):
        pass

    async def rule(self):
        return True


class HelloWorldNode1_1(Node):
    """Hello, World! 示例节点。"""

    parent = "HelloWorldNode1"
    priority = 5

    async def handle(self):
        return None

    async def rule(self):
        return True
