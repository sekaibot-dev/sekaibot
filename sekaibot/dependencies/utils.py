"""SekaiBot 依赖注入。

实现依赖注入相关功能。
"""

import inspect
from collections.abc import AsyncGenerator, Awaitable, Callable, Generator
from contextlib import (
    AbstractAsyncContextManager,
    AbstractContextManager,
    AsyncExitStack,
    asynccontextmanager,
    contextmanager,
)
from typing import Any, TypeVar, Union, cast, get_type_hints
from typing_extensions import override

from sekaibot.utils import get_annotations, sync_ctx_manager_wrapper

_T = TypeVar("_T")
Dependency = Union[  # noqa: UP007
    # Class-based dependencies
    type[_T | AbstractAsyncContextManager[_T] | AbstractContextManager[_T]],
    # Generator-based dependencies
    Callable[[], AsyncGenerator[_T, None]],
    Callable[[], Generator[_T, None, None]],
    # Function-based dependencies
    Callable[..., _T],
    Callable[..., Awaitable[_T]],
]


class InnerDepends:
    """子依赖的内部实现。

    用户无需关注此内部实现。

    Attributes:
        dependency: 依赖类。如果不指定则根据字段的类型注释自动判断。
        use_cache: 是否使用缓存。默认为 `True`。
    """

    dependency: Dependency[Any] | None
    use_cache: bool

    def __init__(
        self, dependency: Dependency[Any] | None = None, *, use_cache: bool = True
    ) -> None:
        self.dependency = dependency
        self.use_cache = use_cache

    @override
    def __repr__(self) -> str:
        attr = getattr(self.dependency, "__name__", type(self.dependency).__name__)
        cache = "" if self.use_cache else ", use_cache=False"
        return f"InnerDepends({attr}{cache})"


def get_dependency_name(dependency: Dependency[Any]) -> str:
    """获取 Dependency[Any] 的名称，正确区分类、函数、实例等"""
    if isinstance(dependency, str):
        return dependency
    if isinstance(dependency, type):
        return dependency.__name__
    if callable(dependency):
        if hasattr(dependency, "__name__"):
            return (
                dependency.__name__ if dependency.__name__ != "<lambda>" else "lambda"
            )
        return dependency.__class__.__name__
    return dependency.__class__.__name__


async def _execute_callable(
    dependent: Callable[..., Any],
    stack: AsyncExitStack | None,
    dependency_cache: dict[Any, Any],
) -> Any:
    """执行可调用对象(函数或 __call__ 方法)，并注入参数。"""
    func_params = inspect.signature(dependent).parameters
    func_args = {}

    for param_name, param in func_params.items():
        try:
            param_type = get_type_hints(dependent).get(param_name)
        except NameError:
            param_type = param.annotation
        if isinstance(param.default, InnerDepends) and param.default.dependency:
            func_args[param_name] = await solve_dependencies(
                param.default.dependency,
                use_cache=param.default.use_cache,
                stack=stack,
                dependency_cache=dependency_cache,
            )
        elif param.default is not inspect.Parameter.empty:
            func_args[param_name] = param.default
        elif param_type in dependency_cache:
            func_args[param_name] = dependency_cache[param_type]
        elif param_name in dependency_cache:
            func_args[param_name] = dependency_cache[param_name]
        else:
            name_cache = {
                get_dependency_name(_cache): _cache for _cache in dependency_cache
            }
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


async def _execute_class(
    dependent: type[_T],
    stack: AsyncExitStack | None,
    dependency_cache: dict[Any, Any],
) -> Any:
    values: dict[str, Any] = {}
    ann = get_annotations(dependent)
    for name, sub_dependent in inspect.getmembers(
        dependent, lambda x: isinstance(x, InnerDepends)
    ):
        assert isinstance(sub_dependent, InnerDepends)
        if sub_dependent.dependency is None:
            dependent_ann = ann.get(name)
            if dependent_ann is None:
                raise TypeError(
                    f"can not resolve dependency for attribute '{name}' in {dependent}"
                )
            sub_dependent.dependency = dependent_ann
        values[name] = await solve_dependencies(
            cast("Dependency[_T]", sub_dependent.dependency),
            use_cache=sub_dependent.use_cache,
            stack=stack,
            dependency_cache=dependency_cache,
        )
    depend_obj = cast(
        "_T | AbstractAsyncContextManager[_T] | AbstractContextManager[_T]",
        dependent.__new__(dependent),  # type: ignore
    )
    for key, value in values.items():
        setattr(depend_obj, key, value)
    depend_obj.__init__()  # pylint: disable=unnecessary-dunder-call

    if isinstance(depend_obj, AbstractAsyncContextManager):
        if stack is None:
            raise TypeError("stack cannot be None when entering an async context")
        depend = await stack.enter_async_context(
            cast("AbstractAsyncContextManager[_T]", depend_obj)
        )
    elif isinstance(depend_obj, AbstractContextManager):
        if stack is None:
            raise TypeError("stack cannot be None when entering a sync context")
        depend = await stack.enter_async_context(
            sync_ctx_manager_wrapper(cast("AbstractContextManager[_T]", depend_obj))
        )
    else:
        depend = depend_obj

    return depend


async def solve_dependencies(
    dependent: Dependency[_T],
    *,
    use_cache: bool = True,
    stack: AsyncExitStack | None = None,
    dependency_cache: dict[Any, Any],
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
        if not dependent.dependency:
            raise TypeError("dependent cannot be None")
        dependent = dependent.dependency

    if not dependent:
        raise TypeError("dependent cannot be None")

    if use_cache and dependent in dependency_cache:
        return dependency_cache[dependent]

    if isinstance(dependent, type):
        # type of dependent is Type[T] (Class, not instance)
        depend = await _execute_class(dependent, stack, dependency_cache)
    elif inspect.isasyncgenfunction(dependent):
        # type of dependent is Callable[[], AsyncGenerator[T, None]]
        if stack is None:
            raise TypeError(
                "stack cannot be None when entering an async generator context"
            )
        cm = asynccontextmanager(dependent)()
        depend = cast("_T", await stack.enter_async_context(cm))
    elif inspect.isgeneratorfunction(dependent):
        # type of dependent is Callable[[], Generator[T, None, None]]
        if stack is None:
            raise TypeError("stack cannot be None when entering a generator context")
        cm = sync_ctx_manager_wrapper(contextmanager(dependent)())
        depend = cast("_T", await stack.enter_async_context(cm))
    elif inspect.iscoroutinefunction(dependent) or inspect.isfunction(dependent):
        # type of dependent is Callable[..., T] | Callable[..., Awaitable[T]]
        depend = await _execute_callable(dependent, stack, dependency_cache)
    elif inspect.ismethod(dependent):
        # type of dependent is a bound method (instance method)
        depend = await _execute_callable(dependent.__func__, stack, dependency_cache)
    elif isinstance(dependent, object) and callable(dependent):
        # type of dependent is an instance with __call__ method (Callable class instance)
        call_method = dependent.__call__  # type: ignore
        if inspect.iscoroutinefunction(call_method) or inspect.isfunction(call_method):
            depend = await _execute_callable(call_method, stack, dependency_cache)
        else:
            raise TypeError(
                f"__call__ method in {dependent.__class__.__name__} is not a valid function"
            )
    elif isinstance(dependent, str):
        name_cache = {
            get_dependency_name(_cache): _cache for _cache in dependency_cache
        }
        if dependent in name_cache:
            depend = dependency_cache[name_cache[dependent]]
    else:
        raise TypeError(f"Dependent {dependent} is not a class, function, or generator")

    dependency_cache[dependent] = depend  # pylint: disable=possibly-used-before-assignment
    return depend
