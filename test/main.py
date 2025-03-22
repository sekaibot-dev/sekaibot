from sekaibot import Bot, Event
import anyio

bot = Bot(config_file="./test/config.toml")


class AEvent:
    type = "a_event"
    adapter = "test_adapter"


bot.run()
