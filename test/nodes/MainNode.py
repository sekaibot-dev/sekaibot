from sekaibot import Node
from sekaibot.rule import StartsWith, CountTrigger
# from sekaibot.rule import rule_at_me


@StartsWith("Hello world")
class HelloWorldNode(Node):
    if_startswith = StartsWith.Checker("Hello, World", True)
    param = StartsWith.Param()

    """Hello, World! 示例节点。"""
    priority = 0

    async def handle(self):
        if key := await self.run(StartsWith._rule_check("Hello, World")):
            param = await self.run(StartsWith.Param)
            print(param)
        return None


@CountTrigger()
class HelloWorldNode1(Node):
    """Hello, World! 示例节点。"""

    parent = "HelloWorldNode"
    priority = 5
    if_counttrigger = CountTrigger.Checker("")
    param = CountTrigger.Param()

    async def handle(self):
        print(self.bot.config.model_dump_json(indent=4))
        return None

    async def rule(self):
        result = await self.run(StartsWith._rule_check("Hello, World"))
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
