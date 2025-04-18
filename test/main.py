# import os
# import sys



from sekaibot import Bot

# sys.path.insert(0, os.path.dirname(__file__))
# Bot.require("sekaibot.plugins.scheduler")
bot = Bot(config_file="./test/config.toml")





bot.run()
