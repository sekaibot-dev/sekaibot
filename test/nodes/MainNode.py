# from typing import Any

from typing import Any

from sekaibot import Event, Node
from sekaibot.adapters.onebot12 import OneBotAdapter


def a(event: Event):
    print(event.get_event_name())


class HelloWorldNode(
    Node[
        Event[OneBotAdapter],
        dict,
        Any
    ]
):
    """Hello, World! 示例节点。"""

    priority = 0

    async def handle(self):
        return None


'''class HelloWorldNode1(Node):
    """Hello, World! 示例节点。"""

    scheduler = SchedulerArg()

    parent = "HelloWorldNode"
    priority = 5
    
    async def handle(self):
        def a(event):
            print("a", event)

        self.scheduler.add_job(a, trigger="interval", seconds=5, args=[self.event])

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
        return True'''
