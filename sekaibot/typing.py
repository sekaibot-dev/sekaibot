from collections.abc import Awaitable, Callable  # type: ignore
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from sekaibot.bot import Bot
    from sekaibot.config import ConfigModel
    from sekaibot.internal.adapter import Adapter
    from sekaibot.internal.event import Event
    from sekaibot.internal.node import Node

__all__ = [
    "EventT",
    "NodeStateT",
    "ConfigT",
    "StateT",
    "DependencyCacheT",
    "RuleCheckerT",
    "PermissionCheckerT",
    "BotHook",
    "EventHook",
]

_T = TypeVar("_T")

EventT = TypeVar("EventT", bound="Event[Adapter[Any, Any]]")
ConfigT = TypeVar("ConfigT", bound="ConfigModel | None")
AdapterT = TypeVar("AdapterT", bound="Adapter[Any, Any]")
NodeT = TypeVar("NodeT", bound="Node")
StateT = TypeVar("StateT", bound="dict[str, dict[str, Any] | Any]")
NodeStateT = TypeVar("NodeStateT")
GlobalStateT = TypeVar("GlobalStateT", bound="dict[str, dict[str, Any]]")
DependencyCacheT = TypeVar("DependencyCacheT", bound="dict")
NameT = TypeVar("NameT", bound="str")

RuleCheckerT = Callable[..., bool | Awaitable[bool]]
PermissionCheckerT = Callable[..., bool | Awaitable[bool]]

HookT = Callable[..., _T] | Callable[..., Awaitable[_T]]
BotHook = HookT[None]
AdapterHook = HookT[None]
EventHook = HookT[None]
NodeHook = HookT[None]
CallingAPIHook = Callable[["Bot", str, dict[str, Any]], Awaitable[Any]]
CalledAPIHook = Callable[["Bot", Exception | None, str, dict[str, Any], Any], Awaitable[Any]]
