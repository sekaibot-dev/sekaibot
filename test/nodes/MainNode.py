# from typing import Any

import random
from typing import Any

from _randsent import generate_sentence

from sekaibot import Event, Node
from sekaibot.adapters.cqhttp.event import MessageEvent
from sekaibot.permission import SuperUser
from sekaibot.rule import Keywords


def a(event: Event):
    print(event.get_event_name())


@Keywords("蒸", "松泽", "松", "lrc", "超")
@SuperUser()
class AutoReply(Node[MessageEvent, dict, Any]):
    """Hello, World! 示例节点。"""

    priority = 1
    zb = Keywords.Param()

    async def handle(self):
        
        keyw = self.zb[0] if self.zb else "蒸"

        await self.reply(
            random.choice(
                (
                    f"{keyw}鞭好粗",
                    f"{keyw}鞭好大",
                    f"香草{keyw}",
                    f"香茶{keyw}",
                    f"{keyw}好可爱",
                    f"{keyw}立了",
                    f"香甜{keyw}",
                    f"{keyw}草我",
                    f"诶我草{keyw}怎么这么坏啊",
                    f"被{keyw}茶了",
                    f"{keyw}是四爱",
                    f"{keyw}是4i",
                    f"{keyw}是南通",
                    f"{keyw}素指南",
                    f"{keyw}就是爱慕",
                    f"{keyw}是正太",
                    f"{keyw}不见了",
                    f"{keyw}蛇了",
                    f"{keyw}北朝的初雪",
                    f"{keyw}北朝的初水",
                    f"{keyw}北朝的豪爽",
                    f"香甜{keyw}的小学",
                    f"北{keyw}顶到职场了",
                    f"想吃{keyw}精",
                    f"想吃{keyw}的大橘瓣",
                    f"想电{keyw}的前列腺",
                    f"{keyw}转过去一下我有急事",
                    f"想吃{keyw}的高玩",
                )
            )
        )


@Keywords("/唐")
@SuperUser()
class RandomSens(Node[MessageEvent, dict, Any]):
    priority = 0
    block = True

    async def handle(self):
        await self.reply(generate_sentence())


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
