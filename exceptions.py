"""SekaiBot 异常。

下列是 SekaiBot 运行过程中可能会抛出的异常。这些异常大部分不需要用户处理， SekaiBot 会自动捕获并处理。
对于适配器开发者，所有适配器抛出的异常都应该继承自 `AdapterException` 。
"""

__all__ = [
    "EventException",
    "SkipException",
    "StopException",
    "SekaiBotException",
    "GetEventTimeout",
    "AdapterException",
    "LoadModuleError",
]


class EventException(BaseException):
    """事件处理过程中由插件抛出的异常，用于控制事件的传播，会被 SekaiBot 自动捕获并处理。"""


class SkipException(EventException):
    """跳过当前插件继续当前事件传播。"""


class JumpToException(EventException):
    """跳转到特定插件并将事件转发到该插件。"""
    def __init__(self, plugin):
        self.plugin = plugin


class PruningException(EventException):
    """在事件处理中需要暂时中断并返回到上一事件处理函数，即剪枝。"""


class StopException(EventException):
    """停止当前事件传播。"""


class SekaiBotException(Exception):  # noqa: N818
    """所有 SekaiBot 发生的异常的基类。"""


class GetEventTimeout(SekaiBotException):
    """当 get 方法超时使被抛出。"""


class AdapterException(SekaiBotException):
    """由适配器抛出的异常基类，所有适配器抛出的异常都应该继承自此类。"""


class LoadModuleError(SekaiBotException):
    """加载模块错误，在指定模块中找不到特定类型的类或模块中存在多个符合条件的类时抛出。"""
