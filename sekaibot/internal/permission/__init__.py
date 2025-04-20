"""SekaiBot 权限基类

所有权限类必须继承 Permission
"""

from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Any, NoReturn, Self, cast, final
from typing_extensions import override

import anyio
from exceptiongroup import BaseExceptionGroup, catch  # noqa: A004

from sekaibot.dependencies import Dependency, Depends, solve_dependencies_in_bot
from sekaibot.exceptions import SkipException
from sekaibot.internal.event import Event
from sekaibot.typing import DependencyCacheT, GlobalStateT, NodeT, PermissionCheckerT

if TYPE_CHECKING:
    from sekaibot.bot import Bot


class Permission:
    """{ref}`nonebot.matcher.Matcher` 权限类。

    当事件传递时，在 {ref}`nonebot.matcher.Matcher` 运行前进行检查。

    Args:
        checkers: PermissionChecker

    用法:
        ```python
        Permission(async_function) | sync_function
        # 等价于
        Permission(async_function, sync_function)
        ```
    """

    __slots__ = ("checkers",)

    def __init__(self, *checkers: PermissionCheckerT) -> None:
        self.checkers: set[PermissionCheckerT] = set(checkers)
        """存储 `PermissionChecker`"""

    @override
    def __repr__(self) -> str:
        return f"Permission({', '.join(repr(checker) for checker in self.checkers)})"

    async def __call__(
        self,
        bot: "Bot",
        event: Event,  # type: ignore
        global_state: GlobalStateT | None = None,
        stack: AsyncExitStack | None = None,
        dependency_cache: DependencyCacheT | None = None,
    ) -> bool:
        """检查是否满足某个权限。

        Args:
            bot: Bot 对象
            event: Event 对象
            global_state: 公共状态
            stack: 异步上下文栈
            dependency_cache: 依赖缓存
        """
        if not self.checkers:
            return True

        result = False

        def _handle_skipped_exception(
            _: BaseExceptionGroup[SkipException],
        ) -> None:
            nonlocal result
            result = False

        async def _run_checker(checker: Dependency[bool]) -> None:
            nonlocal result
            is_passed = await solve_dependencies_in_bot(
                checker,
                bot=bot,
                event=cast("Event[Any]", event),
                global_state=global_state,
                use_cache=False,
                stack=stack,
                dependency_cache=dependency_cache,
            )
            if is_passed:
                result = True
                tg.cancel_scope.cancel()

        with catch({SkipException: _handle_skipped_exception}):
            async with anyio.create_task_group() as tg:
                for checker in self.checkers:
                    tg.start_soon(_run_checker, cast("Dependency[bool]", checker))

        return result

    def __and__(self, other: object) -> NoReturn:
        """禁止 and"""
        raise RuntimeError("And operation between Permissions is not allowed.")

    def __or__(self, other: Self | PermissionCheckerT | None) -> "Permission":
        """or方法"""
        if other is None:
            return self
        if isinstance(other, Permission):
            return Permission(*self.checkers, *other.checkers)
        return Permission(*self.checkers, other)

    def __ror__(self, other: Self | PermissionCheckerT | None) -> "Permission":
        """ror方法"""
        if other is None:
            return self
        if isinstance(other, Permission):
            return Permission(*other.checkers, *self.checkers)
        return Permission(other, *self.checkers)

    def __add__(self, other: Self | PermissionCheckerT | None) -> "Permission":
        """add方法"""
        if other is None:
            return self
        if isinstance(other, Permission):
            return Permission(*self.checkers, *other.checkers)
        return Permission(other, *self.checkers)

    def __iadd__(self, other: Self | PermissionCheckerT) -> Self:
        """iadd方法"""
        self.checkers = self.__add__(other).checkers
        return self

    def __sub__(self, other: Self | PermissionCheckerT) -> NoReturn:
        """紧张 sub"""
        raise RuntimeError("Subtraction operation between permissions is not allowed.")


class PermissionChecker:
    """抽象基类，匹配消息规则。"""

    __perm__: Permission

    def __init__(self, perm: Permission) -> None:
        self.__perm__ = perm

    def __call__(self, cls: NodeT) -> NodeT:
        """将检查器添加到 Node 类中。"""
        if not isinstance(cls, type):
            raise TypeError(f"class should be NodeT, not `{type(cls)}`.")
        if not hasattr(cls, "__node_perm__"):
            cls.__node_perm__ = Permission()
        cls.__node_perm__ += self.__perm__
        return cls

    @classmethod
    def _rule_check(cls, *args: Any, **kwargs: Any) -> Callable[..., Awaitable[bool]]:
        """默认实现检查方法，子类可覆盖。"""
        return cls(*args, **kwargs)._check # type: ignore  # noqa: SLF001

    @classmethod
    def checker(cls, *args: Any, **kwargs: Any) -> bool:
        """默认实现检查方法的依赖注入方法，子类可覆盖。"""
        return Depends(cls._rule_check(*args, **kwargs), use_cache=False)

    @final
    async def _check(
        self,
        bot: "Bot",
        event: Event,  # type: ignore
        global_state: GlobalStateT,
        stack: AsyncExitStack | None = None,
        dependency_cache: DependencyCacheT | None = None,
    ) -> bool:
        """直接运行检查器并获取结果。"""
        return await self.__perm__(
            bot,
            event,
            global_state,
            stack,
            dependency_cache,
        )
