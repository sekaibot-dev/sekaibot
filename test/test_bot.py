import pytest

from sekaibot.bot import Bot
from sekaibot.config import AdapterConfig

from .fake_adapter import FakeAdapter


@pytest.fixture
def bot_instance():
    # 初始化 Bot 实例，避免读取真实配置文件
    return Bot(config_dict={"bot": {"adapters": {"fake"}}})


def test_bot_init_and_config(bot_instance):
    bot = bot_instance
    assert bot.config.bot.adapters == {"fake"}
    # adapters 列表应为空（未加载）
    assert bot.adapters == []


def test_load_adapter_and_get_adapter(bot_instance):
    bot = bot_instance
    bot.load_adapters(FakeAdapter)
    assert any(isinstance(adapter, FakeAdapter) for adapter in bot.adapters)
    adapter = bot.get_adapter("fake")
    assert isinstance(adapter, FakeAdapter)
    # get_adapter by class
    adapter2 = bot.get_adapter(FakeAdapter)
    assert adapter2 is adapter


def test_get_adapter_not_found(bot_instance):
    bot = bot_instance
    with pytest.raises(LookupError):
        bot.get_adapter("notfound")


def test_restart_flag(bot_instance):
    bot = bot_instance
    # 模拟 restart 行为
    bot._should_exit = type(
        "DummyEvent", (), {"is_set": lambda self: False, "set": lambda self: None}
    )()
    bot._restart_flag = False
    bot.restart()
    assert bot._restart_flag is True


def test_shutdown_sets_exit(bot_instance):
    bot = bot_instance

    class DummyEvent:
        def __init__(self):
            self._set = False

        def is_set(self):
            return self._set

        def set(self):
            self._set = True

    bot._should_exit = DummyEvent()
    bot.shutdown()
    assert bot._should_exit.is_set()


def test_load_adapters_multiple(bot_instance):
    bot = bot_instance
    # 加载两次应不会出错
    bot.load_adapters(FakeAdapter)
    bot.load_adapters(FakeAdapter)
    assert len([a for a in bot.adapters if isinstance(a, FakeAdapter)]) >= 1


def test_adapter_config_property(bot_instance):
    bot = bot_instance
    bot.load_adapters(FakeAdapter)
    adapter = bot.get_adapter("fake")
    # config 属性应为 AdapterConfig
    assert isinstance(adapter.config, AdapterConfig)
