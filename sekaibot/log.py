"""SekaiBot 日志模块，基于 structlog。

使用 [`structlog`][structlog] 记录日志信息，支持日志级别过滤、详细信息开关等。

[structlog]: https://www.structlog.org/en/stable/
"""

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
    log_level = structlog.processors.NAME_TO_LEVEL.get(level.casefold(), 0) if isinstance(level, str) else level

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
            level = record.levelname.casefold()
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
