from typing import (
    TYPE_CHECKING, 
    Dict,
    Awaitable, 
    Callable, 
    Optional, 
    TypeVar, 
    Type,
    TypeVar,
    Union,
    Literal, 
    final,
    overload,
    override, 
    TypeAlias
) # type: ignore

if TYPE_CHECKING:
    from typing import Any # type: ignore
    from sekaibot.bot import Bot
    from sekaibot.config import ConfigModel
    from sekaibot.internal.event import Event, EventHandleOption
    from sekaibot.node import Node

__all__ = [
    "TreeType",
    "EventT",
    "StateT",
    "ConfigT",
    "_RuleStateT",
    "_BotStateT",
    "RuleCheckerT",
    "PermissionCheckerT",
    "BotHook",
    "EventHook"
]

EventT = TypeVar("EventT", bound="Event")
ConfigT = TypeVar("ConfigT", bound="ConfigModel | None")
AdapterT = TypeVar("AdapterT")
NodeT = TypeVar("NodeT", bound="Node")
StateT = TypeVar("StateT")
GlobalStateT = TypeVar("GlobalStateT", bound="dict")
_RuleStateT = TypeVar("RuleStateT", bound="dict[str, Any]")
_BotStateT = TypeVar("BotStateT", bound="dict[str, dict[str, Any]]")

RuleCheckerT = Callable[["Bot", "Event[Any]", _RuleStateT], bool | Awaitable[bool]]
PermissionCheckerT = Callable[["Bot", "Event[Any]", _BotStateT], bool | Awaitable[bool]]

BotHook = Callable[["Bot"], Awaitable[None]]
EventHook = Callable[["Event[Any]"], Awaitable[None]]

_T = TypeVar("_T")

class NotGiven:
    """
    A sentinel singleton class used to distinguish omitted keyword arguments
    from those passed in with the value None (which may have different behavior).

    For example:

    ```py
    def get(timeout: int | NotGiven | None = NotGiven()) -> Response: ...


    get(timeout=1)  # 1s timeout
    get(timeout=None)  # No timeout
    get()  # Default timeout behavior, which may not be statically known at the method definition.
    ```
    """

    def __bool__(self) -> Literal[False]:
        return False

    @override
    def __repr__(self) -> str:
        return "NOT_GIVEN"


NotGivenOr = Union[_T, NotGiven]
NOT_GIVEN = NotGiven()


class Omit:
    """In certain situations you need to be able to represent a case where a default value has
    to be explicitly removed and `None` is not an appropriate substitute, for example:

    ```py
    # as the default `Content-Type` header is `application/json` that will be sent
    client.post("/upload/files", files={"file": b"my raw file content"})

    # you can't explicitly override the header as it has to be dynamically generated
    # to look something like: 'multipart/form-data; boundary=0d8382fcf5f8c3be01ca2e11002d2983'
    client.post(..., headers={"Content-Type": "multipart/form-data"})

    # instead you can remove the default `application/json` header by passing Omit
    client.post(..., headers={"Content-Type": Omit()})
    ```
    """

    def __bool__(self) -> Literal[False]:
        return False

