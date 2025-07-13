"""# from typing import Any"""

import random
from typing import Any
from typing_extensions import override

from _sound import get_character_name_list_text, parse_character_command

from sekaibot import Node
from sekaibot.adapter.cqhttp.event import GroupMessageEvent
from sekaibot.permission import User
from sekaibot.rule import Keywords


@Keywords(
    "/开",
    "/关",
    "/角色列表",
    "/角色",
    "蒸",
    "lrc",
    "松泽",
    "思灿",
    "超",
    "香氤",
)
@User("group_596488203", "group_1011357049")
class AutoReply(Node[GroupMessageEvent, dict, Any]):  # type: ignore
    """Hello, World! 示例节点。"""

    priority = 0
    zb = Keywords.Param()

    @override
    async def handle(self) -> None:
        keyw = self.zb[0] if self.zb else "蒸"
        if "sound" not in self.node_state:
            self.node_state["sound"] = False
        if "character" not in self.node_state:
            self.node_state["character"] = "lucy-voice-guangdong-f1"

        if keyw == "/开":
            self.node_state["sound"] = True
            await self.reply("已开启语音回复", at_sender=True)
        elif keyw == "/关":
            self.node_state["sound"] = False
            await self.reply("已关闭语音回复", at_sender=True)
        elif keyw == "/角色列表":
            await self.reply(get_character_name_list_text())
        elif keyw == "/角色":
            if _id := parse_character_command(self.event.get_plain_text()):
                self.node_state["character"] = _id
                await self.reply(f"已成功切换角色：{_id}", at_sender=True)
            else:
                await self.reply("切换失败，请检查", at_sender=True)
        else:
            keyw = "林睿晨" if keyw == "lrc" else keyw
            text = random.choice(  # noqa: S311
                (
                    "{keyw}鞭好粗",
                    "{keyw}鞭好大",
                    "香草{keyw}",
                    "香茶{keyw}",
                    "{keyw}好可爱",
                    "{keyw}立了",
                    "香甜{keyw}",
                    "{keyw}草我",
                    "诶我草{keyw}怎么这么坏啊",
                    "被{keyw}茶了",
                    "{keyw}是四爱",
                    "{keyw}是4i",
                    "{keyw}是南通",
                    "{keyw}素指南",
                    "{keyw}就是爱慕",
                    "{keyw}是正太",
                    "{keyw}不见了",
                    "{keyw}蛇了",
                    "{keyw}北朝的初雪",
                    "{keyw}北朝的初水",
                    "{keyw}北朝的豪爽",
                    "香甜{keyw}的小学",
                    "北{keyw}顶到职场了",
                    "想吃{keyw}精",
                    "想吃{keyw}的大橘瓣",
                    "想电{keyw}的前列腺",
                    "{keyw}转过去一下我有急事",
                    "想吃{keyw}的高玩",
                    "{keyw}很带派",
                    "想吃{keyw}的大汗脚",
                    "被{keyw}口了",
                    "{keyw}是蓝凉",
                )
            ).format(keyw=keyw)
            if self.node_state["sound"] and self.event.message_type == "group":
                await self.call_api(
                    "send_group_ai_record",
                    character=self.node_state["character"],
                    group_id=self.event.group_id,
                    text=text,
                )
            else:
                await self.reply(text)

    @override
    async def rule(self) -> bool:
        return str(self.event.group_id) != "788499440"


@Keywords("芽", "老婆", "我", "妻子")
@User("413966479")
class YanCheng(Node[GroupMessageEvent, dict, Any]):  # type: ignore
    """言承"""

    priority = 0

    keyw = Keywords.Param()

    @override
    async def handle(self) -> None:
        if len(self.keyw) > 1 and "芽" in self.keyw:
            await self.reply("理芽不是言承的……！", at_sender=True)
            self.stop()
