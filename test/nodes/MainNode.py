# from typing import Any

from sekaibot import ConfigModel, Event, Import, Node


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


class _BNode(Node[Event, dict | str, ConfigB]):
    def main(self):
        print(self.name, self.node_state, self.event.get_event_name(), self.config.a)


def a(event: Event):
    print(event.get_event_name())


class HelloWorldNode(Node[Event | BEvent, dict, ConfigA]):
    # if_startswith = StartsWith.Checker("Hello, World", True)
    # param = StartsWith.Param()

    """Hello, World! 示例节点。"""

    a_func = Import(a)

    # B: _BNode = Depends()

    priority = 0

    async def handle(self):
        # print("HelloWorldNode", self._name, self.config.a)
        # self.node_state["async"] = True
        # self.B.Config = ConfigA
        # self.B.main()
        await self.a_func()
        return None


class HelloWorldNode1(Node):
    """Hello, World! 示例节点。"""

    parent = "HelloWorldNode"
    priority = 5

    async def rule(self):
        # result = await self.run(StartsWith._rule_check("Hello, World"))
        return True


class HelloWorldNode2(Node[Event | BEvent, str, dict]):
    """Hello, World! 示例节点。"""

    parent = "HelloWorldNode"
    priority = 2
    # B: _BNode = Depends()

    async def handle(self):
        pass
        # self.node_state = "HelloWorldNode2"
        # self.B.main()

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
