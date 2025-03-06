"""SekaiBot 内部使用的实用工具。"""

import asyncio
import anyio
import importlib
import inspect
import json
import os
import os.path
import sys
import traceback
from abc import ABC
from contextlib import asynccontextmanager
from functools import partial
from importlib.abc import MetaPathFinder
from importlib.machinery import ModuleSpec, PathFinder
from types import GetSetDescriptorType, ModuleType
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    ClassVar,
    ContextManager,
    Coroutine,
    Dict,
    List,
    Set,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)
from typing_extensions import ParamSpec, TypeAlias, TypeGuard

from pydantic import BaseModel

from .config import ConfigModel
from ._types import EventT

if TYPE_CHECKING:
    from os import PathLike

__all__ = [
    "ModulePathFinder",
    "is_config_class",
    "get_classes_from_module",
    "get_classes_from_module_name",
    "PydanticEncoder",
    "samefile",
    "sync_func_wrapper",
    "sync_ctx_manager_wrapper",
    "wrap_get_func",
    "cancel_on_exit",
    "get_annotations",
]

_T = TypeVar("_T")
_P = ParamSpec("_P")
_R = TypeVar("_R")
_TypeT = TypeVar("_TypeT", bound=Type[Any])

StrOrBytesPath: TypeAlias = Union[str, bytes, "PathLike[str]", "PathLike[bytes]"]
TreeType = Dict[_T, Union[Any, "TreeType"]]


class ModulePathFinder(MetaPathFinder):
    """用于查找 KafuBot 组件的元路径查找器。"""

    path: ClassVar[List[str]] = []

    def find_spec(
        self,
        fullname: str,
        path: Optional[Sequence[str]] = None,
        target: Optional[ModuleType] = None,
    ) -> Union[ModuleSpec, None]:
        """用于查找指定模块的 `spec`。"""
        if path is None:
            path = []
        return PathFinder.find_spec(fullname, self.path + list(path), target)


def is_config_class(config_class: Any) -> TypeGuard[Type[ConfigModel]]:
    """判断一个对象是否是配置类。

    Args:
        config_class: 待判断的对象。

    Returns:
        返回是否是配置类。
    """
    return (
        inspect.isclass(config_class)
        and issubclass(config_class, ConfigModel)
        and isinstance(getattr(config_class, "__config_name__", None), str)
        and ABC not in config_class.__bases__
        and not inspect.isabstract(config_class)
    )

def remove_none_attributes(model: Type[BaseModel], exclude: Optional[Set[str]] = None):
    """去除类中值为None的属性

    Args:
        model: BaseModel的子类
        exclude: 无论是否为None都不去除的属性名

    Returns:
        返回是去除类中值为None的属性后的类。
    """
    if exclude is None:
        exclude = set()
    cleaned_data = {
        key: value
        for key, value in model.__dict__.items()
        if key in exclude or value is not None
    }
    for key in list(model.__dict__.keys()):
        delattr(model, key)
    model.__dict__.update(cleaned_data)
    return model

def validate_instance(obj: Any, type_check: Union[Type[Any], Tuple[Type[Any]]]) -> bool:
    """检查对象是否是指定类型的实例，支持单一类型或多个类型的情况。
    
    Args:
        obj: 要检查的对象。
        type_check: 目标类型，可以是一个类型或多个类型的元组。

    Returns: 
        如果 obj 是 type_check 中任意一个类型的实例，则返回 True，否则返回 False。
    """
    if isinstance(type_check, tuple):
        return any(obj.__class__.__name__ == t if isinstance(t, str) else isinstance(obj, t) for t in type_check)
    return obj.__class__.__name__ == type_check if isinstance(type_check, str) else isinstance(obj, type_check)

def get_classes_from_module(module: ModuleType, super_class: _TypeT) -> List[_TypeT]:
    """从模块中查找指定类型的类。

    Args:
        module: Python 模块。
        super_class: 要查找的类的超类。

    Returns:
        返回符合条件的类的列表。
    """
    classes: List[_TypeT] = []
    for _, module_attr in inspect.getmembers(module, inspect.isclass):
        if (
            (inspect.getmodule(module_attr) or module) is module
            and issubclass(module_attr, super_class)
            and module_attr != super_class
            and ABC not in module_attr.__bases__
            and not inspect.isabstract(module_attr)
        ):
            classes.append(cast(_TypeT, module_attr))
    return classes


def get_classes_from_module_name(
    name: str, super_class: _TypeT, *, reload: bool = False
) -> List[Tuple[_TypeT, ModuleType]]:
    """从指定名称的模块中查找指定类型的类。

    Args:
        name: 模块名称，格式和 Python `import` 语句相同。
        super_class: 要查找的类的超类。
        reload: 是否重新加载模块。

    Returns:
        返回由符合条件的类和模块组成的元组的列表。

    Raises:
        ImportError: 当导入模块过程中出现错误。
    """
    try:
        importlib.invalidate_caches()
        module = importlib.import_module(name)
        if reload:
            importlib.reload(module)
        return [(x, module) for x in get_classes_from_module(module, super_class)]
    except KeyboardInterrupt:
        # 不捕获 KeyboardInterrupt
        # 捕获 KeyboardInterrupt 会阻止用户关闭 Python 当正在导入的模块陷入死循环时
        raise
    except BaseException as e:
        raise ImportError(e, traceback.format_exc()) from e


def flatten_tree_with_jumps(
    tree: TreeType[_T]
) -> List[Tuple[_T, int]]:
    """将树按深度优先遍历展开，并计算剪枝后跳转索引。

    该函数遍历给定的树结构，并按深度优先遍历顺序生成节点列表。
    同时，为每个节点计算在剪枝后应跳转的索引，以便提高运行性能。

    适用于运行树，其中每个节点可能执行剪枝操作，剪枝后跳转到最近的兄弟节点，
    如果没有兄弟节点，则跳转到父节点的下一个兄弟节点。若无可跳转位置，则跳转至 -1（表示终止）。

    Args:
        tree: 一个字典形式的树，键代表节点，值可以是子树（字典）或叶子节点。

    Returns:
        一个列表，每个元素是一个元组 (节点, 剪枝后跳转索引)
        其中剪枝后跳转索引指向下一个可执行的节点，-1 表示无可跳转位置。
    """
    ordered_nodes: List[_T] = []  # 存储深度优先遍历顺序
    parent_map: Dict[_T, Union[_T, None]] = {}  # 记录每个节点的父节点
    children_map: Dict[Union[_T, None], List[_T]] = {}  # 记录每个节点的所有子节点

    def dfs(node_dict: TreeType[_T], parent: Union[_T, None] = None) -> None:
        """深度优先遍历树，构建 parent_map 和 children_map"""
        for key, value in node_dict.items():
            ordered_nodes.append(key)
            parent_map[key] = parent  # 记录父节点
            children_map.setdefault(parent, []).append(key)  # 记录子节点
            if isinstance(value, dict):  # 递归遍历子节点
                dfs(value, key)

    dfs(tree)

    def build_jump_map() -> Dict[_T, int]:
        """构建剪枝跳转映射，计算每个节点剪枝后的跳转索引"""
        jump_map: Dict[_T, int] = {node: -1 for node in ordered_nodes}  # 默认剪枝后都终止

        for i in range(len(ordered_nodes) - 1, -1, -1):
            node: _T = ordered_nodes[i]
            parent: Union[_T, None] = parent_map.get(node)

            # 获取兄弟节点
            siblings: List[_T] = children_map.get(parent, [])
            node_pos: int = siblings.index(node)

            # 如果有兄弟节点，跳到最近的兄弟
            if node_pos + 1 < len(siblings):
                jump_map[node] = ordered_nodes.index(siblings[node_pos + 1])
            else:
                # 回溯父节点的兄弟节点
                temp_parent: Union[_T, None] = parent
                while temp_parent is not None:
                    parent_siblings: List[_T] = children_map.get(parent_map.get(temp_parent), [])
                    if temp_parent in parent_siblings:
                        temp_pos: int = parent_siblings.index(temp_parent)
                        if temp_pos + 1 < len(parent_siblings):  # 父节点有兄弟
                            jump_map[node] = ordered_nodes.index(parent_siblings[temp_pos + 1])
                            break
                    temp_parent = parent_map.get(temp_parent)  # 继续向上回溯

        return jump_map

    jump_map: Dict[_T, int] = build_jump_map()

    # 构造最终列表
    return [(node, jump_map[node]) for node in ordered_nodes]


class PydanticEncoder(json.JSONEncoder):
    """用于解析 `pydantic.BaseModel` 的 `JSONEncoder` 类。"""

    def default(self, o: Any) -> Any:
        """返回 `o` 的可序列化对象。"""
        if isinstance(o, BaseModel):
            return o.model_dump(mode="json")
        return super().default(o)


def samefile(path1: StrOrBytesPath, path2: StrOrBytesPath) -> bool:
    """一个 `os.path.samefile` 的简单包装。

    Args:
        path1: 路径1。
        path2: 路径2。

    Returns:
        如果两个路径是否指向相同的文件或目录。
    """
    try:
        return path1 == path2 or os.path.samefile(path1, path2)  # noqa: PTH121
    except OSError:
        return False


def sync_func_wrapper(
    func: Callable[_P, _R], *, to_thread: bool = False
) -> Callable[_P, Coroutine[None, None, _R]]:
    """包装一个同步函数为异步函数。

    Args:
        func: 待包装的同步函数。
        to_thread: 是否在独立的线程中运行同步函数。默认为 `False`。

    Returns:
        异步函数。
    """
    if to_thread:

        async def _wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            loop = asyncio.get_running_loop()
            func_call = partial(func, *args, **kwargs)
            return await loop.run_in_executor(None, func_call)

    else:

        async def _wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            return func(*args, **kwargs)

    return _wrapper


@asynccontextmanager
async def sync_ctx_manager_wrapper(
    cm: ContextManager[_T], *, to_thread: bool = False
) -> AsyncGenerator[_T, None]:
    """将同步上下文管理器包装为异步上下文管理器。

    Args:
        cm: 待包装的同步上下文管理器。
        to_thread: 是否在独立的线程中运行同步函数。默认为 `False`。

    Returns:
        异步上下文管理器。
    """
    try:
        yield await sync_func_wrapper(cm.__enter__, to_thread=to_thread)()
    except Exception as e:
        if not await sync_func_wrapper(cm.__exit__, to_thread=to_thread)(
            type(e), e, e.__traceback__
        ):
            raise
    else:
        await sync_func_wrapper(cm.__exit__, to_thread=to_thread)(None, None, None)

def wrap_get_func(
    func: Optional[Callable[[EventT], Union[bool, Awaitable[bool]]]],
) -> Callable[[EventT], Awaitable[bool]]:
    """将 `get()` 函数接受的参数包装为一个异步函数。

    Args:
        func: `get()` 函数接受的参数。

    Returns:
        异步函数。
    """
    if func is None:
        return sync_func_wrapper(lambda _: True)
    if not asyncio.iscoroutinefunction(func):
        return sync_func_wrapper(func)  # type: ignore
    return func

import anyio
from typing import Union

async def cancel_on_exit(
    condition: anyio.Event | anyio.Condition,
    cancel_scope: anyio.CancelScope
) -> None:
    """当 should_exit 被设置时取消当前的 task group。
    
    支持 `anyio.Event` 和 `anyio.Condition`。
    """
    if isinstance(condition, anyio.Event):
        await condition.wait()
    elif isinstance(condition, anyio.Condition):
        async with condition:
            await condition.wait()
    else:
        raise TypeError(f"`condition` must be anyio.Event or anyio.Condition, not {type(condition)}.")

    cancel_scope.cancel()


if sys.version_info >= (3, 10):  # pragma: no cover
    from inspect import get_annotations
else:  # pragma: no cover

    def get_annotations(
        obj: Union[Callable[..., object], Type[Any], ModuleType],
    ) -> Dict[str, Any]:
        """计算一个对象的标注字典。

        Args:
            obj: 一个可调用对象、类或模块。

        Raises:
            TypeError: `obj` 不是一个可调用对象、类或模块。
            ValueError: 对象的 `__annotations__` 不是一个字典或 `None`。

        Returns:
            对象的标注字典。
        """
        ann: Union[Dict[str, Any], None]

        if isinstance(obj, type):
            # class
            obj_dict = getattr(obj, "__dict__", None)
            if obj_dict and hasattr(obj_dict, "get"):
                ann = obj_dict.get("__annotations__")
                if isinstance(ann, GetSetDescriptorType):
                    ann = None
            else:
                ann = None
        elif isinstance(obj, ModuleType) or callable(obj):
            # this includes types.ModuleType, types.Function, types.BuiltinFunctionType,
            # types.BuiltinMethodType, functools.partial, functools.singledispatch,
            # "class funclike" from Lib/test/test_inspect... on and on it goes.
            ann = getattr(obj, "__annotations__", None)
        else:
            raise TypeError(f"{obj!r} is not a module, class, or callable.")

        if ann is None:
            return {}

        if not isinstance(ann, dict):
            raise ValueError(  # noqa: TRY004
                f"{obj!r}.__annotations__ is neither a dict nor None"
            )

        if not ann:
            return {}

        return dict(ann)

