# import os
# import sys

from chat_module.ChatAPI import ChatAPI
from chat_module.LoadConfig import BaseConfig

from sekaibot import Bot

# sys.path.insert(0, os.path.dirname(__file__))
# Bot.require("sekaibot.plugins.scheduler")
bot = Bot(config_file="./test/config.toml")


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


bot.run()
