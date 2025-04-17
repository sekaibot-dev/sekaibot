"""KafuBot 协议适配器。

所有协议适配器都必须继承自 `Adapter` 基类。
"""

import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, final

import structlog

# from sekaibot.internal.event import Event
from sekaibot.typing import ConfigT
from sekaibot.utils import is_config_class

if TYPE_CHECKING:
    from sekaibot.bot import Bot

__all__ = ["ApiAdapter"]

logger = structlog.stdlib.get_logger()

if os.getenv("SEKAIBOT_DEV") == "1":  # pragma: no cover
    # 当处于开发环境时，使用 pkg_resources 风格的命名空间包
    __import__("pkg_resources").declare_namespace(__name__)


class ApiAdapter(Generic[ConfigT], ABC):
    """API适配器基类。

    Attributes:
        name: 适配器的名称。
        bot: 当前的机器人对象。
    """

    name: str
    bot: "Bot"
    Config: type[ConfigT]

    def __init__(self, bot: "Bot") -> None:
        """初始化。

        Args:
            bot: 当前机器人对象。
        """
        if not hasattr(self, "name"):
            self.name = self.__class__.__name__
        self.bot: Bot = bot
        # self.handle_event = self.bot.handle_event

    @property
    def config(self) -> ConfigT:
        """适配器配置。"""
        default: Any = None
        config_class = getattr(self, "Config", None)
        if is_config_class(config_class):
            return config_class(
                **getattr(
                    self.bot.config.apiadapter,
                    config_class.__config_name__,
                    default,
                )
            )
        return default

    @final
    async def safe_run(self) -> None:
        """附带有异常处理地安全运行适配器。"""
        try:
            await self.run()
        except Exception:
            logger.exception("Run adapter failed", adapter_name=self.__class__.__name__)

    @abstractmethod
    async def run(self) -> None:
        """适配器运行方法，适配器开发者必须实现该方法。

        适配器运行过程中保持保持运行，当此方法结束后， KafuBot 不会自动重新启动适配器。
        """
        raise NotImplementedError

    async def startup(self) -> None:
        """在适配器开始运行前运行的方法，用于初始化适配器。

        KafuBot 依次运行并等待所有适配器的 `startup()` 方法，待运行完毕后再创建 `run()` 任务。
        """

    async def shutdown(self) -> None:
        """在适配器结束运行时运行的方法，用于安全地关闭适配器。

        KafuBot 在接收到系统的结束信号后依次运行并等待所有适配器的 `shutdown()` 方法。
        当强制退出时此方法可能未被执行。
        """
