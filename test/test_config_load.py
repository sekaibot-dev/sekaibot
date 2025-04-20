import pytest
from pydantic import ValidationError

from sekaibot.config import (
    AgentConfig,
    BotConfig,
    DatabaseConfig,
    LLMConfig,
    LogConfig,
    MainConfig,
    MongoDBConfig,
    PermissionConfig,
    PromptConfig,
    RedisConfig,
    RuleConfig,
    SQLConfig,
    ToolConfig,
)


def test_main_config_default_values():
    config = MainConfig()
    assert isinstance(config.bot, BotConfig)
    assert config.bot.log.level == "DEBUG"
    assert isinstance(config.rule, RuleConfig)
    assert config.rule.command_start == {"/"}
    assert isinstance(config.permission, PermissionConfig)
    assert config.permission.superusers == set()


def test_bot_config_field_types():
    bot_cfg = BotConfig()
    assert isinstance(bot_cfg.nodes, set)
    assert isinstance(bot_cfg.node_dirs, set)
    assert isinstance(bot_cfg.adapters, set)
    assert isinstance(bot_cfg.superusers, set)
    assert isinstance(bot_cfg.log, LogConfig)
    assert bot_cfg.adapter_max_retries >= 0


def test_rule_config_customization():
    rule = RuleConfig(command_start={"!"}, command_sep={":"})
    assert rule.command_start == {"!"}
    assert rule.command_sep == {":"}


def test_permission_config_customization():
    perm = PermissionConfig(superusers={"alice", "bob"})
    assert perm.superusers == {"alice", "bob"}


def test_llm_config_literal_validation():
    llm_cfg = LLMConfig()
    assert llm_cfg.llm_type == "openai"
    with pytest.raises(ValidationError):
        LLMConfig(llm_type="other")


def test_tool_config_collections():
    tool_cfg = ToolConfig(tools={"t1", "t2"}, tool_dirs=set())
    assert tool_cfg.tools == {"t1", "t2"}
    assert isinstance(tool_cfg.tool_dirs, set)


def test_prompt_config_default():
    prompt = PromptConfig()
    assert prompt.name == "Sekai"
    assert isinstance(prompt.symbol_conversation, list)


def test_agent_config_nested():
    agent = AgentConfig()
    assert isinstance(agent.llm, LLMConfig)
    assert isinstance(agent.tool, ToolConfig)
    assert isinstance(agent.prompt, PromptConfig)


def test_sql_config_and_database_config():
    sql_cfg = SQLConfig(db_type="sql", connection_string="sqlite:///:memory:")
    db_cfg = DatabaseConfig(config=sql_cfg)
    assert db_cfg.config.db_type == "sql"
    assert db_cfg.config.connection_string == "sqlite:///:memory:"


def test_redis_config_and_database_config():
    redis_cfg = RedisConfig(db_type="redis", url="redis://localhost/1")
    db_cfg = DatabaseConfig(config=redis_cfg)
    assert db_cfg.config.db_type == "redis"
    assert db_cfg.config.url == "redis://localhost/1"


def test_mongodb_config_and_database_config():
    mongo_cfg = MongoDBConfig(
        db_type="mongodb",
        connection_string="mongodb://localhost:27017",
        session_id="sid",
        database_name="db",
        collection_name="col",
        create_index=False,
    )
    db_cfg = DatabaseConfig(config=mongo_cfg)
    assert db_cfg.config.db_type == "mongodb"
    assert db_cfg.config.connection_string == "mongodb://localhost:27017"
    assert db_cfg.config.session_id == "sid"


def test_invalid_database_config_type():
    with pytest.raises(ValidationError):
        DatabaseConfig(config={"db_type": "notype"})


def test_main_config_dict_loading():
    d = {
        "bot": {"event_queue_size": 10, "superusers": {"admin"}},
        "rule": {"command_start": {"#"}, "command_sep": {";"}},
        "permission": {"superusers": {"admin", "root"}},
    }
    config = MainConfig(**d)
    assert config.bot.event_queue_size == 10
    assert config.rule.command_start == {"#"}
    assert config.permission.superusers == {"admin", "root"}
