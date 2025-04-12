from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from itertools import chain
from typing import TYPE_CHECKING, Generic, NoReturn, Self, TypeVar, Union, final

import anyio
from exceptiongroup import BaseExceptionGroup, catch

from sekaibot.dependencies import Dependency, Depends, solve_dependencies_in_bot
from sekaibot.exceptions import SkipException
from sekaibot.internal.event import Event
from sekaibot.typing import DependencyCacheT, GlobalStateT, NodeT, RuleCheckerT, StateT

if TYPE_CHECKING:
    from sekaibot.bot import Bot

__all__ = ["Rule", "RuleChecker", "MatchRule"]


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

    def __init__(self, *checkers: Union["Rule", RuleCheckerT, Dependency[bool]]) -> None:
        self.checkers: set[Dependency[bool]] = set(
            chain.from_iterable(
                checker.checkers if isinstance(checker, Rule) else {checker} for checker in checkers
            )
        )
        """存储 `RuleChecker`"""

    def __repr__(self) -> str:
        return f"Rule({', '.join(repr(checker) for checker in self.checkers)})"

    async def __call__(
        self,
        bot: "Bot",
        event: Event,
        state: StateT,
        global_state: GlobalStateT,
        stack: AsyncExitStack | None = None,
        dependency_cache: DependencyCacheT | None = None,
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
            exc_group: BaseExceptionGroup[SkipException],
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

    def __and__(self, other: Self | RuleCheckerT | None) -> Self:
        if other is None:
            return self
        elif isinstance(other, Rule):
            return Rule(*self.checkers, *other.checkers)
        else:
            return Rule(*self.checkers, other)

    def __rand__(self, other: Self | RuleCheckerT | None) -> Self:
        if other is None:
            return self
        elif isinstance(other, Rule):
            return Rule(*other.checkers, *self.checkers)
        else:
            return Rule(other, *self.checkers)

    def __or__(self, other: object) -> NoReturn:
        raise RuntimeError("Or operation between rules is not allowed.")

    def __add__(self, other: Self | RuleCheckerT) -> Self:
        if other is None:
            return self
        elif isinstance(other, Rule):
            return Rule(*self.checkers, *other.checkers)
        else:
            return Rule(*self.checkers, other)

    def __iadd__(self, other: Self | RuleCheckerT) -> Self:
        return self.__add__(other)

    def __sub__(self, other: Self | RuleCheckerT) -> NoReturn:
        raise RuntimeError("Subtraction operation between rules is not allowed.")


ArgsT = TypeVar("T")
ParamT = TypeVar("P")


class RuleChecker(Generic[ArgsT]):
    """抽象基类，匹配消息规则。"""

    def __init__(self, rule: Rule) -> None:
        self.__rule__ = rule

    def __call__(self, cls: NodeT) -> NodeT:
        """将检查器添加到 Node 类中。"""
        if not isinstance(cls, type):
            raise TypeError(f"class should be NodeT, not `{type(cls)}`.")
        if not hasattr(cls, "__node_rule__"):
            cls.__node_rule__ = Rule()
        cls.__node_rule__ += self.__rule__
        return cls

    @classmethod
    def _rule_check(cls, *args: ArgsT, **kwargs) -> Callable[..., Awaitable[bool]]:
        """默认实现检查方法，子类可覆盖。"""
        return cls(*args, **kwargs)._check

    @classmethod
    def Checker(cls, *args: ArgsT, **kwargs) -> bool:
        """默认实现检查方法的依赖注入方法，子类可覆盖。"""
        return Depends(cls._rule_check(*args, **kwargs), use_cache=False)

    @final
    async def _check(
        self,
        bot: "Bot",
        event: Event,
        state: StateT,
        global_state: GlobalStateT,
        stack: AsyncExitStack | None = None,
        dependency_cache: DependencyCacheT | None = None,
    ) -> bool:
        """直接运行检查器并获取结果。"""
        return await self.__rule__(
            bot,
            event,
            state,
            global_state,
            stack,
            dependency_cache,
        )
