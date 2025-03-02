# config.py
import os
from typing import (
    List, 
    Dict, 
    Literal, 
    Optional, 
    Set, 
    Union, 
    Any
)

from pydantic import BaseModel, ConfigDict, DirectoryPath, Field

__all__ = [
    "ConfigModel",
    "LogConfig",
    "BotConfig",
    "PluginConfig",
    "AdapterConfig",
    "MainConfig",
]


class ConfigModel(BaseModel):
    """KafuBot 配置模型。

    Attributes:
        __config_name__: 配置名称。
    """

    model_config = ConfigDict(extra="allow")

    __config_name__: str = ""


class LogConfig(ConfigModel):
    """SekaiBot 日志相关设置。

    Attributes:
        level: 日志级别。
        verbose_exception: 详细的异常记录，设置为 `True` 时会在日志中添加异常的 Traceback。
    """

    level: Union[str, int] = "DEBUG"
    verbose_exception: bool = False

class BotConfig(ConfigModel):
    """Bot 相关设置。"""

    log: LogConfig | None = None


class LLMConfig(ConfigModel):
    """LLM 配置。

    Attributes:
    """

    llm_type: Literal["openai"] = "openai"
    api_key: str = "sk-dFzsKInVuNhZhAt8KpV4qXhyWeFbME0RYxiGJLXjDHrhirkb"#os.getenv("OPENAI_API_KEY", "your-openai-api-key")
    base_url: str = "https://api.chatanywhere.tech/v1"
    model: str = "gpt-4o-mini"


class SQLConfig(ConfigModel):
    """SQL 配置。
    Attributes:
        connection_string: String parameter configuration for connecting
            to the database.
        table_name: Table name used to save data.
        session_id_field_name: The name of field of `session_id`.
        engine_args: Additional configuration for creating database engines.
        async_mode: Whether it is an asynchronous connection.
    """
    connection_string: Optional[str] = None,
    table_name: str = "message_store",
    session_id_field_name: str = "session_id",
    engine_args: Optional[Dict[str, Any]] = None,
    async_mode: Optional[bool] = None, 

class RedisConfig(ConfigModel):
    """Redis 配置。

    Attributes:
        url: String parameter configuration for connecting to the redis.
        key_prefix: The prefix of the key, combined with `session id` to form the key.
        ttl: Set the expiration time of `key`, the unit is seconds.
    """
    url: str = "redis://localhost:6379/0"
    key_prefix: str = "message_store:"
    ttl: Optional[int] = None

class MongoDBConfig(ConfigModel):
    """MongoDB 配置。

    Attributes:
        connection_string: connection string to connect to MongoDB
        database_name: name of the database to use
        collection_name: name of the collection to use
        create_index: whether to create an index with name SessionId. Set to False if
            such an index already exists.
    """
    connection_string: str
    session_id: str
    database_name: str = "chat_history"
    collection_name: str = "message_store"
    create_index: bool = True

class DatabaseConfig(ConfigModel):
    """Database 配置。

    Attributes:
    """
    db_type: Literal["sql", "redis", "mongodb"] = "redis"
    config: SQLConfig | RedisConfig | MongoDBConfig

class CharacterConfig(ConfigModel):
    """角色信息配置。
    
    Attributes:"""

    name: str = "Sekai"
    role_definition: str = (
        "你是一个善解人意、幽默风趣的AI助理，会根据用户的上下文对话内容进行自然回答。"
        "请注意对话场景的合理性，并结合用户和系统信息。"
    )
    symbol_conversation: List[Dict[str, str | List[str | Dict]]] = [
        {"input": "你好", "output": "你好，很高兴能帮助你"}
    ]

class MainConfig(ConfigModel):
    """SekaiBot 主体配置。"""
    bot: BotConfig = BotConfig()
    llm: LLMConfig = LLMConfig()
    database: DatabaseConfig = DatabaseConfig()
    character: CharacterConfig = CharacterConfig()
