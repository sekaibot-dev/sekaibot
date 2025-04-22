"""SekaiBot Rule类

所有 Rule 类的基类
"""

from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from copy import deepcopy
from typing import TYPE_CHECKING, Any, NoReturn, Self, cast, final
from typing_extensions import override

import anyio
from exceptiongroup import catch

from sekaibot.dependencies import Dependency, Depends, solve_dependencies_in_bot
from sekaibot.exceptions import SkipException
from sekaibot.internal.event import Event
from sekaibot.typing import GlobalStateT, NodeT, RuleCheckerT, StateT

if TYPE_CHECKING:
    from sekaibot.bot import Bot

__all__ = ["Rule", "RuleChecker"]


class Rule:
    """{ref}`nonebot.matcher.Matcher` 规则类。

    当事件传递时，在 {ref}`nonebot.matcher.Matcher` 运行前进行检查。

    Args:
        *checkers: RuleChecker

    用法:
        ```python
        Rule(async_function) & sync_function
        # 等价于
        Rule(async_function, sync_function)
        ```
    """

    __slots__ = ("checkers",)

    def __init__(self, *checkers: RuleCheckerT | Dependency[bool]) -> None:
        self.checkers: set[Dependency[bool]] = set(
            cast("tuple[Dependency[bool]]", checkers)
        )
        """存储 `RuleChecker`"""

    @override
    def __repr__(self) -> str:
        return f"Rule({', '.join(repr(checker) for checker in self.checkers)})"

    async def __call__(
        self,
        bot: "Bot",
        event: Event[Any],
        state: StateT,
        global_state: GlobalStateT,
        stack: AsyncExitStack | None = None,
        dependency_cache: dict[Any, Any] | None = None,
    ) -> bool:
        """检查是否符合所有规则

        Args:
            bot: Bot 对象
            event: Event 对象
            state: 当前 State
            global_state: 当前机器人公用 State
            stack: 异步上下文栈
            dependency_cache: 依赖缓存
        """
        if not self.checkers:
            return True

        result = True

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
                event=event,
                state=state,
                global_state=global_state,
                use_cache=False,
                stack=stack,
                dependency_cache=dependency_cache,
            )
            if not is_passed:
                result = False
                tg.cancel_scope.cancel()

        with catch({SkipException: _handle_skipped_exception}):
            async with anyio.create_task_group() as tg:
                for checker in self.checkers:
                    tg.start_soon(_run_checker, checker)

        return result

    def __and__(self, other: "Rule | RuleCheckerT | None") -> "Rule":
        """and方法"""
        if other is None:
            return self
        if isinstance(other, Rule):
            return Rule(*self.checkers, *other.checkers)
        return Rule(*self.checkers, other)

    def __rand__(self, other: "Rule | RuleCheckerT | None") -> "Rule":
        """rand方法"""
        if other is None:
            return self
        if isinstance(other, Rule):
            return Rule(*other.checkers, *self.checkers)
        return Rule(other, *self.checkers)

    def __or__(self, other: object) -> NoReturn:
        """or方法"""
        raise RuntimeError("Or operation between rules is not allowed.")

    def __add__(self, other: "Rule | RuleCheckerT | None") -> "Rule":
        """add方法"""
        if other is None:
            return self
        if isinstance(other, Rule):
            return Rule(*self.checkers, *other.checkers)
        return Rule(*self.checkers, other)

    def __iadd__(self, other: "Rule | RuleCheckerT | None") -> Self:
        """iadd方法"""
        if other is None:
            return self
        if isinstance(other, Rule):
            self.checkers.update(other.checkers)
        else:
            self.checkers.add(cast("Dependency[bool]", other))
        return self

    def __sub__(self, other: object) -> NoReturn:
        """禁止 sub"""
        raise RuntimeError("Subtraction operation between rules is not allowed.")


class RuleChecker:
    """抽象基类，匹配消息规则。"""

    _rule: Rule

    def __init__(self, rule: Rule) -> None:
        self._rule = rule

    def __call__(self, cls: NodeT) -> NodeT:
        """将检查器添加到 Node 类中。"""
        if "__node_rule__" not in cls.__dict__:
            cls.__node_rule__ = deepcopy(cls.__node_rule__)
        cls.__node_rule__ += self._rule
        return cls

    @classmethod
    def _rule_check(cls, *args: Any, **kwargs: Any) -> Callable[..., Awaitable[bool]]:
        """默认实现检查方法，子类可覆盖。"""
        return cls(*args, **kwargs)._check

    @classmethod
    def Checker(cls, *args: Any, **kwargs: Any) -> bool:
        """默认实现检查方法的依赖注入方法，子类可覆盖。"""
        return Depends(cls._rule_check(*args, **kwargs), use_cache=False)  # type: ignore

    @final
    async def _check(
        self,
        bot: "Bot",
        event: Event[Any],
        state: StateT,
        global_state: GlobalStateT,
        stack: AsyncExitStack | None = None,
        dependency_cache: dict[Any, Any] | None = None,
    ) -> bool:
        """直接运行检查器并获取结果。"""
        return await self._rule(
            bot,
            event,
            state,
            global_state,
            stack,
            dependency_cache,
        )
