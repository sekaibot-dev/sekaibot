from functools import cached_property
from typing import Any, final

from chat_module.config import CharacterConfig, MySQLConfig, RedisConfig
from chat_module.FileOperation import add_read_task

from sekaibot import Bot
from sekaibot.typing import ConfigT
from sekaibot.utils import is_config_class


class BaseConfig:
    def __init__(self, _bot: Bot):
        self.bot = _bot

    def __enter__(self):
        # 进入上下文时执行的操作
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # 离开上下文时执行的操作
        pass

    def _load_config(self, config_class, default=None):
        """通用配置加载方法"""
        default: Any = None
        if is_config_class(config_class):
            return getattr(
                self.bot.config.plugin,
                config_class.__config_name__,
                default,
            )
        return default

    @final
    @property
    def _character_config(self) -> ConfigT:
        character = self._load_config(CharacterConfig)
        config = CharacterConfig
        if character["config_path"] != "":
            c_config = add_read_task(character["config_path"])["chat_config"]
            config.talk_set = c_config["character_set"].get("talk_set")
            config.info_set = c_config["character_set"].get("info_set")
            config.analyze_set = c_config["analyze_set"].get("analyze_set")
            return config
        else:
            return character

    @final
    @cached_property
    def _mysql_config(self) -> ConfigT:
        return self._load_config(MySQLConfig)

    @final
    @cached_property
    def _redis_config(self) -> ConfigT:
        return self._load_config(RedisConfig)
