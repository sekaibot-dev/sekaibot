'''from structlog.stdlib import get_logger, BoundLogger
import structlog
from typing import (
    TYPE_CHECKING
)

if TYPE_CHECKING:
    from sekaibot.bot import Bot

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
'''
"""NoneBot 日志模块，基于 structlog。

使用 [`structlog`][structlog] 记录日志信息，支持日志级别过滤、详细信息开关等。

[structlog]: https://www.structlog.org/en/stable/
"""
"""本模块定义了 NoneBot 的日志记录 Logger（使用 structlog）。"""

import sys
import logging
import structlog
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from structlog.typing import FilteringBoundLogger


def configure_logging(level="INFO", verbose_exception=True):
    """配置 structlog 日志系统。

    参数:
        level (str | int): 日志级别，如 `"INFO"`, `"DEBUG"` 或 数值 `10, 20, 30...`
        verbose_exception (bool): 是否记录详细异常信息。
    """
    log_level = structlog.processors.NAME_TO_LEVEL.get(level.lower(), 0) if isinstance(level, str) else level

    # **创建 FilteringBoundLogger，控制日志级别**
    wrapper_class = structlog.make_filtering_bound_logger(log_level)

    # **如果 verbose_exception=False，则屏蔽 exception 记录**
    if not verbose_exception:
        class BoundLoggerWithoutException(wrapper_class):  # type: ignore
            """不记录异常的 wrapper_class。"""
            exception = wrapper_class.error
            aexception = wrapper_class.aerror  # 异步异常

        wrapper_class = BoundLoggerWithoutException

    structlog.configure(wrapper_class=wrapper_class)


default_format = structlog.dev.ConsoleRenderer(colors=True)


class StructLogHandler(logging.Handler):
    """Python `logging` 日志 → `structlog` 适配器，将 `logging` 事件转发到 `structlog`。"""

    def emit(self, record: logging.LogRecord):
        try:
            level = record.levelname.lower()
        except ValueError:
            level = "info"

        structlog.get_logger(record.name).bind(
            exc_info=record.exc_info
        ).log(level, record.getMessage())


'''structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),  # JSON 格式日志
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)'''

logger: "FilteringBoundLogger" = structlog.get_logger("nonebot")
"""NoneBot 日志记录器对象。"""

logging.getLogger().handlers.clear()

logging.getLogger().addHandler(StructLogHandler())
