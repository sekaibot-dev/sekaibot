import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from sekaibot.bot import Bot
from sekaibot.dependencies import Depends
from sekaibot.log import StructLogHandler, logger
from sekaibot.plugin import Plugin

from .config import SchedulerConfig

__all__ = ["SchedulerArg"]




def SchedulerArg():
    async def wrapper(
        bot: Bot = Depends(Bot),  # noqa: B008
    ) -> AsyncIOScheduler:
        if isinstance(bot_scheduler := bot.get_plugins(Scheduler.name), Scheduler):
            return bot_scheduler.scheduler
        raise RuntimeError("Scheduler not found.")

    return Depends(wrapper)


class Scheduler(Plugin[SchedulerConfig]):
    """Scheduler 组件，使用 APScheduler 实现定时任务调度器。"""

    name: str = "Scheduler"
    bot: "Bot"
    Config: type[SchedulerConfig] = SchedulerConfig

    scheduler: AsyncIOScheduler

    def __init__(self, bot: "Bot"):
        super().__init__(bot)
        Bot.bot_run_hook(self.startup)

    async def startup(self):

        self.scheduler = AsyncIOScheduler()
        self.scheduler.configure(self.config.apscheduler_config)

        aps_logger = logging.getLogger("apscheduler")
        aps_logger.setLevel(self.config.apscheduler_log_level)
        aps_logger.handlers.clear()
        aps_logger.addHandler(StructLogHandler())
        if self.config.apscheduler_autostart:
            if not self.scheduler.running:
                self.scheduler.start()
                logger.info("Running Scheduler...")
            Bot.bot_exit_hook(self.shutdown)

    async def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Stopping Scheduler...")


Bot.require_plugin(Scheduler)