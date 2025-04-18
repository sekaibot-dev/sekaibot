from typing import Any

from chat_module.ChatAPI import ChatAPI
from chat_module.LoadConfig import BaseConfig
from chat_module.MessageEvent import ChatHandler

from sekaibot import Bot, Node
from sekaibot.adapter.cqhttp.event import MessageEvent
from sekaibot.dependencies import Depends

# from sekaibot.permission import SuperUser
from sekaibot.rule import ToMe


@Bot.bot_run_hook
async def hook_func(_bot: Bot):
    with BaseConfig(_bot) as config:
        _bot.global_state["chat_system"] = ChatAPI(
            character_config=config._character_config,
            mysql_config=config._mysql_config,
            redis_config=config._redis_config,
        )


@Bot.bot_exit_hook
async def exit_hook(_bot: Bot):
    await _bot.global_state["chat_system"].close()


# @SuperUser()
@ToMe()
class NormalMsg(Node[MessageEvent, dict, Any]):
    priority: int = 2
    block: bool = False

    # limit = Depends(MessageLimit)
    response = Depends(ChatHandler)

    async def handle(self) -> None:
        if "/clear" in self.event.get_plain_text():
            await self.response._clear_chat_memory_tool(None)
            return
        await self.response.respond_to_message(if_music=True, if_img=False)

    async def rule(self) -> bool:
        print(self.event.is_tome())
        if "请使用最新版本" in self.event.get_plain_text():
            return False
        if self.event.user_id == 2854196310:
            return False
        return True
