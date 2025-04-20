import inspect
from collections.abc import Awaitable, Callable
from typing import Any, Generic

import anyio
from anyio.lowlevel import checkpoint
from typing_extensions import override

from sekaibot import Adapter, Event, Node
from sekaibot.typing import ConfigT, StateT

EventFactory = Callable[
    ["FakeAdapter"],
    Event["FakeAdapter"] | None | Awaitable[Event["FakeAdapter"] | None],
]


class FakeAdapter(Adapter[Event[Any], None]):
    """用于测试的适配器。"""

    name: str = "fake_adapter"
    event_factories: tuple[EventFactory, ...] = ()
    handle_get: bool = True

    @override
    async def run(self) -> None:
        for event_factory in self.event_factories:
            event_factory_call = event_factory(self)
            if inspect.isawaitable(event_factory_call):
                event = await event_factory_call
            elif isinstance(event_factory_call, Event):
                event = event_factory_call
            else:
                continue

            if isinstance(event, Event):
                await self.handle_event(event, handle_get=self.handle_get)

        for _ in range(10):  # 尽可能让其他任务执行完毕后再退出
            await checkpoint()

        await anyio.sleep(3)
        self.bot.shutdown()

    @override
    async def _call_api(self, api, **params):
        pass

    @override
    async def send(self, event, message, **kwargs):
        pass


def fake_adapter_class_factory(
    *event_factories: EventFactory, handle_get: bool = True
) -> type[FakeAdapter]:
    return type(
        "FakeAdapter",
        (FakeAdapter,),
        {"event_factories": event_factories, "handle_get": handle_get},
    )


class FakeMessageEvent(Event[FakeAdapter]):
    message: str = "test"

    @override
    def get_plain_text(self) -> str:
        return self.message

    @override
    def get_event_description(self):
        return self.message

    @override
    def get_message(self):
        return self.message

    @override
    def get_session_id(self):
        return "session_id"

    @override
    def get_user_id(self):
        return "user_id"

    @override
    def is_tome(self):
        return True


def fake_message_event_factor(adapter: FakeAdapter, message: str = "test") -> FakeMessageEvent:
    return FakeMessageEvent(adapter=adapter, type="message", message=message)


class BaseTestNode(
    Generic[StateT, ConfigT],
    Node[FakeMessageEvent, StateT, ConfigT],
):
    @override
    async def handle(self) -> None:
        pass

    @override
    async def rule(self) -> bool:
        return isinstance(self.event, FakeMessageEvent)
