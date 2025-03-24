#from typing import Any

from sekaibot import ConfigModel, Depends, Event, Node, SonNode


class ConfigA(ConfigModel):
    __config_name__ = "a"
    a: str = None
class ConfigB(ConfigModel):
    __config_name__ = "b"
    a: str = None


# from sekaibot.rule import rule_at_me
class BEvent(Event):
    type: str = "a_event"
    adapter: str = "test_adapter"


class BNode(SonNode[Event, str, ConfigB]):
    def main(self):
        print(self.node_state, self.event.get_event_name(), self.config.a)


class HelloWorldNode(Node[Event | BEvent, dict, ConfigA]):
    # if_startswith = StartsWith.Checker("Hello, World", True)
    # param = StartsWith.Param()

    """Hello, World! 示例节点。"""

    B: BNode = Depends()

    priority = 0

    async def handle(self):
        print("HelloWorldNode", self.name, self.config.a)
        self.node_state["async"] = True
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
