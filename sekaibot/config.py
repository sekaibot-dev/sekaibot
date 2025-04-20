"""SekaiBot 配置。

SekaiBot 使用 [pydantic](https://pydantic-docs.helpmanual.io/) 来读取配置。
"""

from pydantic import BaseModel, ConfigDict, DirectoryPath, Field

__all__ = [
    "BotConfig",
    "ConfigModel",
    "LogConfig",
    "MainConfig",
    "NodeConfig",
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

    level: str | int = "DEBUG"
    verbose_exception: bool = False


class BotConfig(ConfigModel):
    """Bot 相关设置。"""

    event_queue_size: int = Field(default=0, ge=0)
    nodes: set[str] = Field(default_factory=set)
    node_dirs: set[DirectoryPath] = Field(default_factory=set)
    adapters: set[str] = Field(default_factory=set)
    adapter_max_retries: int = Field(default=0, ge=0)
    superusers: set[str] = Field(default_factory=set)
    log: LogConfig = LogConfig()


'''
class LLMConfig(ConfigModel):
    """LLM 配置。

    Attributes:
    """

    llm_type: Literal["openai"] = "openai"
    api_key: str = "sk-dFzsKInVuNhZhAt8KpV4qXhyWeFbME0RYxiGJLXjDHrhirkb"  # os.getenv("OPENAI_API_KEY", "your-openai-api-key")
    base_url: str = "https://api.chatanywhere.tech/v1"
    model: str = "gpt-4o-mini"


class ToolConfig(ConfigModel):
    """Tool 配置。

    Attributes:
    """

    tools: set[str] = Field(default_factory=set)
    tool_dirs: set[DirectoryPath] = Field(default_factory=set)


class PromptConfig(ConfigModel):
    """角色信息配置。

    Attributes:
        name: 角色名字
        role_definition: 角色定义
        symbol_conversation: 角色对话样例
    """

    name: str | None = "Sekai"
    role_definition: str | None = (
        "你是一个善解人意、幽默风趣的AI助理，会根据用户的上下文对话内容进行自然回答。"
        "请注意对话场景的合理性，并结合用户和系统信息。"
    )
    symbol_conversation: list[dict[str, str | list[str | dict]]] | None = [
        {"input": "你好", "output": "你好，很高兴能帮助你"}
    ]


class AgentConfig(ConfigModel):
    """Agent 配置。

    Attributes:

    """

    llm: LLMConfig = LLMConfig()
    tool: ToolConfig = ToolConfig()
    prompt: PromptConfig = PromptConfig()


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

    db_type: Literal["sql"]
    connection_string: str | None = (None,)
    table_name: str = ("message_store",)
    session_id_field_name: str = ("session_id",)
    engine_args: dict[str, Any] | None = (None,)
    async_mode: bool | None = (None,)


class RedisConfig(ConfigModel):
    """Redis 配置。

    Attributes:
        url: String parameter configuration for connecting to the redis.
        key_prefix: The prefix of the key, combined with `session id` to form the key.
        ttl: set the expiration time of `key`, the unit is seconds.
    """

    db_type: Literal["redis"]
    url: str = "redis://localhost:6379/0"
    key_prefix: str = "message_store:"
    ttl: int | None = None


class MongoDBConfig(ConfigModel):
    """MongoDB 配置。

    Attributes:
        connection_string: connection string to connect to MongoDB
        database_name: name of the database to use
        collection_name: name of the collection to use
        create_index: whether to create an index with name SessionId. set to False if
            such an index already exists.
    """

    db_type: Literal["mongodb"]
    connection_string: str
    session_id: str
    database_name: str = "chat_history"
    collection_name: str = "message_store"
    create_index: bool = True


DatabaseConfigType = Annotated[
    SQLConfig | RedisConfig | MongoDBConfig,
    Field(discriminator="db_type"),
]


class DatabaseConfig(ConfigModel):
    """Database 配置。

    Attributes:
        config: SQLConfig | RedisConfig | MongoDBConfig
    """

    config: DatabaseConfigType'''


class AdapterConfig(ConfigModel):
    """适配器配置。"""


class NodeConfig(ConfigModel):
    """节点配置。"""


class PluginConfig(ConfigModel):
    """节点配置。"""


class RuleConfig(ConfigModel):
    """规则配置。

    Attributes:
        command_start: 命令的起始标记，用于判断一条消息是不是命令。
        command_sep: 命令的分隔标记，用于将文本形式的命令切分为元组 (实际的命令名) 。
    """

    command_start: set[str] = {"/"}
    command_sep: set[str] = {"."}


class PermissionConfig(ConfigModel):
    """权限配置。

    Attributes:
        superusers: 超级管理员列表。
    """

    superusers: set[str] = Field(default_factory=set)


class MainConfig(ConfigModel):
    """SekaiBot 主体配置。"""

    bot: BotConfig = BotConfig()
    node: NodeConfig = NodeConfig()
    adapter: AdapterConfig = AdapterConfig()
    plugin: PluginConfig = PluginConfig()
    rule: RuleConfig = RuleConfig()
    permission: PermissionConfig = PermissionConfig()

