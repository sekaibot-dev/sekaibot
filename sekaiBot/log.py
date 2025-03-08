from structlog.stdlib import get_logger, BoundLogger
import structlog
from typing import (
    TYPE_CHECKING
)

if TYPE_CHECKING:
    from .bot import Bot

class Logger:

    bot: "Bot"
    logger: BoundLogger

    def __init__(
        self,
        bot: "Bot"
    ):
        self.bot = bot
        self.logger = get_logger()

    def _reload_logger(self):
        """重载logger。"""
        if self.bot.config.bot.log is not None:
            log_level = 0
            if isinstance(self.bot.config.bot.log.level, int):
                log_level = self.bot.config.bot.log.level
            elif isinstance(self.bot.config.bot.log.level, str):
                log_level = structlog.processors.NAME_TO_LEVEL[
                    self.bot.config.bot.log.level.lower()
                ]

            wrapper_class = structlog.make_filtering_bound_logger(log_level)

            if not self.bot.config.bot.log.verbose_exception:

                class BoundLoggerWithoutException(wrapper_class):  # type: ignore
                    """用于不记录异常的 wrapper_class。"""

                    exception = wrapper_class.error
                    aexception = wrapper_class.aerror

                wrapper_class = BoundLoggerWithoutException

            structlog.configure(wrapper_class=wrapper_class)

    def bind(self, **kwargs) -> "Logger":
        """
        Bind additional context to the logger.
        """
        self.logger = self.logger.bind(**kwargs)
        return self

    def info(self, message: str, **kwargs):
        """
        Log an info-level message.
        """
        self.logger.info(message, **kwargs)

    def debug(self, message: str, **kwargs):
        """
        Log a debug-level message.
        """
        self.logger.debug(message, **kwargs)

    def warning(self, message: str, **kwargs):
        """
        Log a warning-level message.
        """
        self.logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs):
        """
        Log an error-level message.
        """
        self.logger.error(message, **kwargs)

    def exception(self, message: str, **kwargs):
        """
        Log an exception with traceback.
        """
        self.logger.exception(message, **kwargs)
