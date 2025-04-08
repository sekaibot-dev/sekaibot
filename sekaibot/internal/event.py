"""SekaiBot 事件。

事件类的基类。适配器开发者应实现此事件类基类的子类。
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, NamedTuple, override

from pydantic import BaseModel, ConfigDict, Field

from sekaibot.typing import AdapterT

from .message import Message

__all__ = ["Event", "EventHandleOption"]


class Event(ABC, BaseModel, Generic[AdapterT]):
    """事件类的基类。

    Attributes:
        adapter: 产生当前事件的适配器对象。
        type: 事件类型。
        __handled__: 表示事件是否被处理过了，用于适配器处理。警告：请勿手动更改此属性的值。
    """

    model_config = ConfigDict(extra="allow")

    type: str | None
    __handled__: bool = False

    if TYPE_CHECKING:
        adapter: AdapterT
    else:
        adapter: Any = Field(..., exclude=True)

    @override
    def __str__(self) -> str:
        return f"Event<{self.type}>: {self.get_event_description()}"

    @override
    def __repr__(self) -> str:
        return self.__str__()

    def get_event_name(self) -> str:
        """获取事件名称的方法。"""
        return self.__class__.__name__

    @abstractmethod
    def get_event_description(self) -> str:
        """获取事件描述的方法，通常为事件具体内容。"""
        raise NotImplementedError

    def get_log_string(self) -> str:
        """获取事件日志信息的方法。

        通常你不需要修改这个方法，只有当希望 NoneBot 隐藏该事件日志时，
        可以抛出 `NoLogException` 异常。

        异常:
            NoLogException: 希望 NoneBot 隐藏该事件日志
        """
        return f"Event<{self.type}>: {self.get_event_description()}"

    @abstractmethod
    def get_user_id(self) -> str | None:
        """获取事件主体 id 的方法，通常是用户 id 。"""
        raise NotImplementedError

    @abstractmethod
    def get_session_id(self) -> str | None:
        """获取会话 id 的方法，用于判断当前事件属于哪一个会话，
        通常是用户 id、群组 id 组合。
        """
        raise NotImplementedError

    @abstractmethod
    def get_message(self) -> Message | None:
        """获取事件消息内容的方法。"""
        raise NotImplementedError

    def get_plain_text(self) -> str:
        """获取消息纯文本的方法。

        通常不需要修改，默认通过 `get_message().get_plain_text` 获取。
        """
        return self.get_message().get_plain_text()

    @abstractmethod
    def is_tome(self) -> bool:
        """获取事件是否与机器人有关的方法。"""
        raise NotImplementedError


class EventHandleOption(NamedTuple):
    """事件处理选项。

    Attributes:
        event: 当前事件。
        handle_get: 当前事件是否可以被 get 方法捕获。
    """

    event: Event[Any]
    handle_get: bool