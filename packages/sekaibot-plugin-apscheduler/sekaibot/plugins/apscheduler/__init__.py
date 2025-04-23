"""SekaiBot AsyncIOScheduler 插件"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from sekaibot.bot import Bot
from sekaibot.dependencies import Depends
from sekaibot.log import StructLogHandler, logger
from sekaibot.plugin import Plugin

from .config import APSchedulerConfig

__all__ = ["APSchedulerArg"]


def APSchedulerArg() -> AsyncIOScheduler:
    """通过依赖注入获取 AsyncIOScheduler"""

    async def wrapper(
        bot: Bot = Depends(Bot),  # noqa: B008 # type: ignore
    ) -> AsyncIOScheduler:
        if isinstance(bot_scheduler := bot.get_plugin(APScheduler.name), APScheduler):
            return bot_scheduler.scheduler
        raise RuntimeError("Scheduler not found.")

    return Depends(wrapper)


class APScheduler(Plugin[APSchedulerConfig]):
    """Scheduler 组件，使用 APScheduler 实现定时任务调度器。"""

    name: str = "APScheduler"
    bot: "Bot"
    Config: type[APSchedulerConfig] = APSchedulerConfig

    scheduler: AsyncIOScheduler

    def __init__(self, bot: "Bot") -> None:
        super().__init__(bot)
        Bot.bot_run_hook(self.startup)

    async def startup(self) -> None:
        self.scheduler = AsyncIOScheduler()
        self.scheduler.configure(self.config.apscheduler_config)  # type: ignore

        aps_logger = logging.getLogger("apscheduler")
        aps_logger.setLevel(self.config.apscheduler_log_level)
        aps_logger.handlers.clear()
        aps_logger.addHandler(StructLogHandler())
        if self.config.apscheduler_autostart:
            if not self.scheduler.running: # type: ignore
                self.scheduler.start() # type: ignore
                logger.info("Running APScheduler...")
            Bot.bot_exit_hook(self.shutdown)

    async def shutdown(self) -> None:
        if self.scheduler.running: # type: ignore
            self.scheduler.shutdown() # type: ignore
            logger.info("Stopping APScheduler...")


Bot.require_plugin(APScheduler)
