from collections.abc import Callable
from typing import Any

from fake_adapter import FakeAdapter, fake_adapter_class_factory, fake_message_event_factor

from sekaibot import Adapter, Bot, Event, Node
from sekaibot.typing import StateT


def test_bot_run_hook() -> None:
    hook_call_list: list[Callable[..., Any]] = []

    @Bot.bot_startup_hook
    async def bot_startup_hook(_bot: Bot):
        hook_call_list.append(bot_startup_hook)

    @Bot.bot_run_hook
    async def bot_run_hook(_bot: Bot) -> None:
        hook_call_list.append(bot_run_hook)

    @Bot.bot_exit_hook
    async def bot_exit_hook(_bot: Bot) -> None:
        hook_call_list.append(bot_exit_hook)

    @Bot.adapter_startup_hook
    async def adapter_startup_hook(_adapter: Adapter) -> None:
        hook_call_list.append(adapter_startup_hook)

    @Bot.adapter_run_hook
    async def adapter_run_hook(_adapter: Adapter) -> None:
        hook_call_list.append(adapter_run_hook)

    @Bot.adapter_shutdown_hook
    async def adapter_shutdown_hook(_adapter: Adapter) -> None:
        hook_call_list.append(adapter_shutdown_hook)

    @Bot.event_preprocessor_hook
    async def event_preprocessor_hook(_event: Event) -> None:
        hook_call_list.append(event_preprocessor_hook)

    @Bot.event_postprocessor_hook
    async def event_postprocessor_hook(_event: Event) -> None:
        hook_call_list.append(event_postprocessor_hook)

    @Bot.node_preprocessor_hook
    async def node_preprocessor_hook(_node: Node, _bot: Bot, _event: Event, _state: StateT):
        hook_call_list.append(node_preprocessor_hook)

    @Bot.node_postprocessor_hook
    async def node_postprocessor_hook(
        _node: Node, _exc: Exception, _bot: Bot, _event: Event, _state: StateT
    ):
        hook_call_list.append(node_postprocessor_hook)

    @FakeAdapter.calling_api_hook
    async def calling_api_hook(_bot: Bot, _api: str, _params: dict[str, Any]):
        hook_call_list.append(calling_api_hook)

    @FakeAdapter.called_api_hook
    async def called_api_hook(
        _bot: Bot, _exc: Exception, _api: str, _params: dict[str, Any], _result: Any
    ):
        hook_call_list.append(called_api_hook)

    bot = Bot(config_file="./test/config.toml")
    bot.load_adapters(fake_adapter_class_factory(fake_message_event_factor))
    bot.run()
    print(hook_call_list)

    assert hook_call_list == [
        bot_startup_hook,
        bot_run_hook,
        adapter_startup_hook,
        adapter_run_hook,
        event_preprocessor_hook,
        node_preprocessor_hook,
        calling_api_hook,
        called_api_hook,
        node_postprocessor_hook,
        event_postprocessor_hook,
        adapter_shutdown_hook,
        bot_exit_hook,
    ]
