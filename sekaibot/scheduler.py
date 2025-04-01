import logging
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from sekaibot.dependencies import Depends
from sekaibot.log import StructLogHandler, logger

if TYPE_CHECKING:
    from sekaibot.bot import Bot


def Scheduler():
    def wrapper(
        bot: "Bot" = Depends("Bot")  # noqa: B008
    ) -> AsyncIOScheduler:
        if isinstance(bot_scheduler := bot.plugin_dict["scheduler"], SekaibotScheduler):
            return bot_scheduler.scheduler
        else:
            bot.plugin_dict["scheduler"] = SekaibotScheduler(bot)
            return bot.plugin_dict["scheduler"].scheduler
        
    return Depends(wrapper)


class SekaibotScheduler:
    bot: "Bot"
    scheduler: AsyncIOScheduler

    def __init__(self, bot: "Bot"):
        self.bot = bot
        config = bot.config.bot.scheduler

        self.scheduler = AsyncIOScheduler()
        self.scheduler.configure(config.apscheduler_config)

        aps_logger = logging.getLogger("apscheduler")
        aps_logger.setLevel(config.apscheduler_log_level)
        aps_logger.handlers.clear()
        aps_logger.addHandler(StructLogHandler())

        if config.apscheduler_autostart:
            self.bot.bot_run_hook(self.startup)
            self.bot.bot_exit_hook(self.shutdown)

    async def startup(self):
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler Started...")

    async def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler Shutdown")