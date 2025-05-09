"""SekaiBot 类型提示支持。

此模块定义了部分 SekaiBot 使用的类型。
"""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, TypeVar

if TYPE_CHECKING:
    from sekaibot.adapter import Adapter
    from sekaibot.config import ConfigModel
    from sekaibot.internal.event import Event
    from sekaibot.internal.node import Node

__all__ = [
    "BotHook",
    "ConfigT",
    "EventHook",
    "EventT",
    "NodeStateT",
    "PermissionCheckerT",
    "RuleCheckerT",
    "StateT",
]

_T = TypeVar("_T")

EventT = TypeVar("EventT", bound="Event[Any]")
ConfigT = TypeVar("ConfigT", bound="ConfigModel | None")
AdapterT = TypeVar("AdapterT", bound="Adapter[Any, Any]")
NodeT = TypeVar("NodeT", bound="Node[Any, Any, Any]")
StateT = TypeVar("StateT", bound="dict[str, dict[str, Any] | Any]")
NodeStateT = TypeVar("NodeStateT")
GlobalStateT = TypeVar("GlobalStateT", bound="dict[str, dict[str, Any]]")
NameT = TypeVar("NameT", bound="str")

RuleCheckerT = Callable[..., bool | Awaitable[bool]]
PermissionCheckerT = Callable[..., bool | Awaitable[bool]]

HookT = Callable[..., _T] | Callable[..., Awaitable[_T]]
BotHook = HookT[None]
AdapterHook = HookT[None]
EventHook = HookT[None]
NodeHook = HookT[None]
CallingAPIHook = Callable[["Adapter[Any, Any]", str, dict[str, Any]], Awaitable[Any]]
CalledAPIHook = Callable[
    ["Adapter[Any, Any]", Exception | None, str, dict[str, Any], Any], Awaitable[Any]
]
