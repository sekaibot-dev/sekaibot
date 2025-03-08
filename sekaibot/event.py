"""AliceBot 事件。

事件类的基类。适配器开发者应实现此事件类基类的子类。
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, NamedTuple, Optional, Union
from typing_extensions import Self, override

from pydantic import BaseModel, ConfigDict

from alicebot.typing import AdapterT

__all__ = ["Event", "EventHandleOption", "MessageEvent"]


class Event(ABC, BaseModel, Generic[AdapterT]):
    """事件类的基类。

    Attributes:
        adapter: 产生当前事件的适配器对象。
        type: 事件类型。
        __handled__: 表示事件是否被处理过了，用于适配器处理。警告：请勿手动更改此属性的值。
    """

    model_config = ConfigDict(extra="allow")

    if TYPE_CHECKING:
        adapter: AdapterT
    else:
        adapter: Any
    type: Optional[str]
    __handled__: bool = False

    @override
    def __str__(self) -> str:
        return f"Event<{self.type}>"

    @override
    def __repr__(self) -> str:
        return self.__str__()


class EventHandleOption(NamedTuple):
    """事件处理选项。

    Attributes:
        event: 当前事件。
        handle_get: 当前事件是否可以被 get 方法捕获。
    """

    event: Event[Any]
    handle_get: bool