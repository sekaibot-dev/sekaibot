from sekaibot import Node, Bot, Depends
# from MainNode import HelloWorldNode1
# from sekaibot.rule import rule


class HelloWorldNode2_1(Node):
    """Hello, World! 示例节点。"""

    bot: Bot = Depends()
    parent = "HelloWorldNode1"
    priority = 2

    async def handle(self):
        print(self.bot, self.event)
        return None

    async def rule(self):
        return True


class HelloWorldNode1_2(Node):
    """Hello, World! 示例节点。"""

    parent = "HelloWorldNode2"
    priority = 1

    async def handle(self):
        return None

    async def rule(self):
        return True


class HelloWorldNode2_2(Node):
    """Hello, World! 示例节点。"""

    parent = "HelloWorldNode2"
    priority = 2

    async def handle(self):
        return None

    async def rule(self):
        return True
