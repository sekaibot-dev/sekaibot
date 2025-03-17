"""SekaiBot 依赖注入。

实现依赖注入相关功能。
"""

import inspect
import sys
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncContextManager,
    AsyncGenerator,
    Callable,
    Awaitable,
    ContextManager,
    Dict,
    Generator,
    Optional,
    Type,
    TypeVar,
    Union,
    Generic,
    cast,
    get_type_hints
)

from sekaibot.utils import get_annotations, sync_ctx_manager_wrapper
from sekaibot.internal.event import Event
from sekaibot.typing import StateT, GlobalStateT, _RuleStateT, _PermStateT
if TYPE_CHECKING:
    from sekaibot.bot import Bot

_T = TypeVar("_T")

Dependency = Union[
    # Class-based dependencies
    Type[Union[_T, AsyncContextManager[_T], ContextManager[_T]]],
    # Generator-based dependencies
    Callable[[], AsyncGenerator[_T, None]],
    Callable[[], Generator[_T, None, None]],
    # Function-based dependencies (带参数)
    Callable[..., _T],
    Callable[..., Awaitable[_T]],
]


__all__ = ["Depends"]


class InnerDepends:
    """子依赖的内部实现。

    用户无需关注此内部实现。

    Attributes:
        dependency: 依赖类。如果不指定则根据字段的类型注释自动判断。
        use_cache: 是否使用缓存。默认为 `True`。
    """

    dependency: Optional[Dependency]
    use_cache: bool

    def __init__(
        self, dependency: Optional[Dependency] = None, *, use_cache: bool = True
    ) -> None:
        if isinstance(dependency, InnerDepends):
            self.dependency = dependency.dependency
            self.use_cache = dependency.use_cache
        self.dependency = dependency
        self.use_cache = use_cache

    def __repr__(self) -> str:
        attr = getattr(self.dependency, "__name__", type(self.dependency).__name__)
        cache = "" if self.use_cache else ", use_cache=False"
        return f"InnerDepends({attr}{cache})"


def Depends(  # noqa: N802 # pylint: disable=invalid-name
    dependency: Optional[Dependency[_T]] = None, *, use_cache: bool = True
) -> _T:
    """子依赖装饰器。

    Args:
        dependency: 依赖类。如果不指定则根据字段的类型注释自动判断。
        use_cache: 是否使用缓存。默认为 `True`。

    Returns:
        返回内部子依赖对象。
    """
    return InnerDepends(dependency=dependency, use_cache=use_cache)  # type: ignore

def get_dependency_name(dependency: Dependency[Any]) -> str:
    """获取 Dependency[Any] 的名称，正确区分类、函数、实例等"""

    if isinstance(dependency, str):
        return dependency
    if isinstance(dependency, type):
        return dependency.__name__
    if callable(dependency):
        if hasattr(dependency, "__name__"):
            return dependency.__name__ if dependency.__name__ != "<lambda>" else "lambda"
        return dependency.__class__.__name__
    return dependency.__class__.__name__


async def _execute_callable(
    dependent: Callable[..., Any], 
    stack: AsyncExitStack, 
    dependency_cache: Dict[Dependency[Any], Any]
) -> Any:
    """执行可调用对象（函数或 __call__ 方法），并注入参数。"""
    func_params = inspect.signature(dependent).parameters
    func_args = {}

    for param_name, param in func_params.items():
        param_type = get_type_hints(dependent).get(param_name)
        if isinstance(param.default, InnerDepends):
            func_args[param_name] = await solve_dependencies(
                param.default.dependency, 
                use_cache=param.default.use_cache,
                stack=stack, 
                dependency_cache=dependency_cache
            )
        elif param.default is not inspect.Parameter.empty:
            func_args[param_name] = param.default
        elif param_type in dependency_cache:
            func_args[param_name] = dependency_cache[param_type]
        elif param_name in dependency_cache:
            func_args[param_name] = dependency_cache[param_name]
        else:
            name_cache = {get_dependency_name(_cache): _cache for _cache in dependency_cache.keys()}
            if isinstance(param_type, str) and param_type in name_cache:
                func_args[param_name] = dependency_cache[name_cache[param_type]]
            elif param_name in name_cache:
                func_args[param_name] = dependency_cache[name_cache[param_name]]
            else:
                raise TypeError(
                    f"Cannot resolve parameter '{param_name}' for dependency '{dependent.__name__}'"
                )

    if inspect.iscoroutinefunction(dependent):
        return await dependent(**func_args)
    return dependent(**func_args)

async def solve_dependencies(
    dependent: Dependency[_T],
    *,
    use_cache: bool,
    stack: Optional[AsyncExitStack] = None,
    dependency_cache: Dict[Dependency[Any], Any],
) -> _T:
    """解析子依赖，包括 `__call__` 方法的可调用类实例。

    Args:
        dependent: 依赖对象，可能是类、类实例、函数、生成器等。
        use_cache: 是否使用缓存，避免重复解析。
        stack: `AsyncExitStack` 对象，用于管理上下文依赖。
        dependency_cache: 已解析的依赖缓存。

    Raises:
        TypeError: `dependent` 解析失败。

    Returns:
        解析完成依赖的对象。
    """
    if isinstance(dependent, InnerDepends):
        use_cache = dependent.use_cache
        dependent = dependent.dependency
        
    if dependent is None:
        raise TypeError("dependent cannot be None")

    if use_cache and dependent in dependency_cache:
        return dependency_cache[dependent]

    if isinstance(dependent, type):
        # type of dependent is Type[T] (Class, not instance)
        values: Dict[str, Any] = {}
        ann = get_annotations(dependent)
        for name, sub_dependent in inspect.getmembers(
            dependent, lambda x: isinstance(x, InnerDepends)
        ):
            assert isinstance(sub_dependent, InnerDepends)
            if sub_dependent.dependency is None:
                dependent_ann = ann.get(name)
                if dependent_ann is None:
                    raise TypeError(f"can not resolve dependency for attribute '{name}' in {dependent}")
                sub_dependent.dependency = dependent_ann
            values[name] = await solve_dependencies(
                sub_dependent.dependency,
                use_cache=sub_dependent.use_cache,
                stack=stack,
                dependency_cache=dependency_cache,
            )
        depend_obj = cast(
            Union[_T, AsyncContextManager[_T], ContextManager[_T]],
            dependent.__new__(dependent),  # pyright: ignore
        )
        for key, value in values.items():
            setattr(depend_obj, key, value)
        depend_obj.__init__()

        if isinstance(depend_obj, AsyncContextManager):
            if stack is None:
                raise TypeError("stack cannot be None when entering an async context")
            depend = await stack.enter_async_context(depend_obj)  # pyright: ignore
        elif isinstance(depend_obj, ContextManager):
            if stack is None:
                raise TypeError("stack cannot be None when entering a sync context")
            depend = await stack.enter_async_context(  # pyright: ignore
                sync_ctx_manager_wrapper(depend_obj)
            )
        else:
            depend = depend_obj
    elif isinstance(dependent, object) and hasattr(dependent, "__call__") and callable(dependent):
        # type of dependent is an instance with __call__ method (Callable class instance)
        call_method = dependent.__call__
        if inspect.iscoroutinefunction(call_method) or inspect.isfunction(call_method):
            depend = await _execute_callable(call_method, stack, dependency_cache)
        else:
            raise TypeError(f"__call__ method in {dependent.__class__.__name__} is not a valid function")
    elif inspect.iscoroutinefunction(dependent) or inspect.isfunction(dependent):
        # type of dependent is Callable[..., T] | Callable[..., Awaitable[T]]
        depend = await _execute_callable(dependent, stack, dependency_cache)
    elif inspect.isasyncgenfunction(dependent):
        # type of dependent is Callable[[], AsyncGenerator[T, None]]
        if stack is None:
            raise TypeError("stack cannot be None when entering an async generator context")
        cm = asynccontextmanager(dependent)()
        depend = cast(_T, await stack.enter_async_context(cm))
    elif inspect.isgeneratorfunction(dependent):
        # type of dependent is Callable[[], Generator[T, None, None]]
        if stack is None:
            raise TypeError("stack cannot be None when entering a generator context")
        cm = sync_ctx_manager_wrapper(contextmanager(dependent)())
        depend = cast(_T, await stack.enter_async_context(cm))
    elif isinstance(dependent, str):
        name_cache = {get_dependency_name(_cache): _cache for _cache in dependency_cache.keys()}
        if dependent in name_cache:
            depend = dependency_cache[name_cache[dependent]]
    else:
        raise TypeError(f"Dependent {dependent} is not a class, function, or generator")

    dependency_cache[dependent] = depend
    return depend  # pyright: ignore


async def solve_dependencies_in_bot(
    dependent: Dependency[_T],
    *,
    bot: "Bot",
    event: Event,
    state: Optional[StateT] = None,
    global_state: Optional[GlobalStateT] = None,
    rule_state: Optional[_RuleStateT] = None,
    perm_state: Optional[_PermStateT] = None,
    use_cache: bool = True,
    stack: Optional[AsyncExitStack] = None,
    dependency_cache: Optional[Dict[Dependency[Any], Any]] = None,
) -> _T:
    """解析子依赖。
    
    此方法强制要求 `bot`、`event`、`state`、`global_state` 作为参数，以确保依赖解析的严谨性。

    Args:
        dependent: 需要解析的依赖。
        bot: 机器人实例，必须提供。
        event: 事件对象，必须提供。
        state: 为节点提供的状态信息，默认为 `None`。
        global_state: 为节点提供的全局状态，可选，默认为 `None`。
        rule_state: 为规则解析器提供状态，可选，默认为 `None`。
        perm_state: 权限管理器状态，可选，默认为 `None`。
        use_cache: 是否使用缓存，默认为 `True`。
        stack: 异步上下文管理器，可选。
        dependency_cache: 依赖缓存，如果未提供，则自动创建新字典。

    Returns:
        解析后的依赖对象。
    """
    from sekaibot.bot import Bot

    if dependency_cache is None:
        dependency_cache = {}
    dependency_cache.update({
        Bot: bot,
        Event: event,
        "bot": bot,
        "event": event,
    })
    if state is not None: dependency_cache.update({
        StateT: state,
        "state": state,
    })
    if global_state is not None: dependency_cache.update({
        GlobalStateT: global_state,
        "global_state": global_state,
    })
    if rule_state is not None: dependency_cache.update({
        _RuleStateT: rule_state,
    })
    if perm_state is not None: dependency_cache.update({
        _PermStateT: perm_state,
    })
    return await solve_dependencies(
        dependent, use_cache=use_cache, stack=stack, dependency_cache=dependency_cache
    )
