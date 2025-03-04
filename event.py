"""KafuBot 事件。

事件类的基类。适配器开发者应实现此事件类基类的子类。
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Generic, Optional, Union
from typing_extensions import Self

from pydantic import BaseModel, ConfigDict

__all__ = ["Info", "Comm", "MessageEvent"]



class Event(ABC, BaseModel):
    """事件类的基类。

    Attributes:
        adapter: 产生当前事件的适配器对象。
        type: 事件类型。
        __handled__: 表示事件是否被处理过了，用于适配器处理。警告：请勿手动更改此属性的值。
    """

    model_config = ConfigDict(extra="allow")

    type: Optional[str]
    __handled__: bool = False

    def __str__(self) -> str:
        """返回事件的文本表示。

        Returns:
            事件的文本表示。
        """
        return f"Event<{self.type}>"

    def __repr__(self) -> str:
        """返回事件的描述。

        Returns:
            事件的描述。
        """
        return self.__str__()