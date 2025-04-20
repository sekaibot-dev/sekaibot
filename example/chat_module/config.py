from chat_module.FileOperation import add_read_task, add_write_task

from sekaibot import ConfigModel


class CharacterConfig(ConfigModel):
    __config_name__ = "chat_config"
    config_path: str = ""
    talk_set: dict = {}
    info_set: dict = {}
    analyze_set: str = ""


class MySQLConfig(ConfigModel):
    __config_name__ = "mysql_config"
    host: str = ("localhost",)
    port: int = (3306,)
    user: str = ("root",)
    password: str = ("00000000",)
    db: str = ("",)
    charset: str = "utf8mb4"


class RedisConfig(ConfigModel):
    __config_name__ = "redis_config"
    host: str = ("localhost",)
    port: int = (6379,)
    db: int = (0,)
