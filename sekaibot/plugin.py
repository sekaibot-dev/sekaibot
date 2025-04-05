from typing import TYPE_CHECKING, Any, Generic, final

from sekaibot.typing import ConfigT
from sekaibot.utils import is_config_class

if TYPE_CHECKING:
    from sekaibot.bot import Bot

__all__ = ["Plugin"]


class Plugin(Generic[ConfigT]):
    """SekaiBot 通用基类。

    Attributes:
        name: 类的名称。
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

    @final
    @property
    def config(self) -> ConfigT:
        """类配置。"""
        default: Any = None
        config_class = getattr(self, "Config", None)
        if is_config_class(config_class):
            return getattr(
                self.bot.config.plugin,
                config_class.__config_name__,
                default,
            )
        return default
