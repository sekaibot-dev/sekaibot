"""SekaiBot 异常。

下列是 SekaiBot 运行过程中可能会抛出的异常。这些异常大部分不需要用户处理， SekaiBot 会自动捕获并处理。
对于适配器开发者，所有适配器抛出的异常都应该继承自 `AdapterException` 。
"""

from typing import Any

__all__ = [
    "EventException",
    "SkipException",
    "StopException",
    "RejectException",
    "SekaiBotException",
    "GetEventTimeout",
    "AdapterException",
    "LoadModuleError",
]


class EventException(BaseException):
    """事件处理过程中由节点抛出的异常，用于控制事件的传播，会被 SekaiBot 自动捕获并处理。"""


class IgnoreException(EventException):
    """忽略此事件。"""


class MockApiException(EventException):
    """指示 NoneBot 阻止本次 API 调用或修改本次调用返回值，并返回自定义内容。
    可由 api hook 抛出。

    Args:
        result: 返回的内容
    """

    def __init__(self, result: Any):
        self.result = result

    def __repr__(self) -> str:
        return f"MockApiException(result={self.result!r})"


class SkipException(EventException):
    """跳过当前节点继续当前事件传播。"""


class JumpToException(EventException):
    """跳转到特定节点并将事件转发到该节点。"""


class PruningException(EventException):
    """在事件处理中需要暂时中断并返回到上一事件处理函数，即剪枝。"""


class StopException(EventException):
    """停止当前事件传播。"""


class FinishException(EventException):
    """结束本节点人物并继续事件传播。"""


class RejectException(EventException):
    """拒绝执行当前节点，并重新获取事件再次进入节点。"""


class SekaiBotException(Exception):  # noqa: N818
    """所有 SekaiBot 发生的异常的基类。"""


class GetEventTimeout(SekaiBotException):
    """当 get 方法超时使被抛出。"""


class AdapterException(SekaiBotException):
    """由适配器抛出的异常基类，所有适配器抛出的异常都应该继承自此类。"""


class LoadModuleError(SekaiBotException):
    """加载模块错误，在指定模块中找不到特定类型的类或模块中存在多个符合条件的类时抛出。"""
