from contextlib import AsyncExitStack
from abc import ABC, abstractmethod
from typing import (
    TYPE_CHECKING, 
    Any, 
    NoReturn, 
    Optional, 
    Type, 
    Self, 
    Callable, 
    Awaitable, 
    Generic, 
    TypeVar, 
    final
)

import anyio
from exceptiongroup import BaseExceptionGroup, catch

from sekaibot.dependencies import Dependency, Depends, solve_dependencies_in_bot
from sekaibot.exceptions import SkipException
from sekaibot.internal.event import Event
from itertools import chain
from sekaibot.typing import RuleCheckerT, StateT, GlobalStateT, NodeT

if TYPE_CHECKING:
    from sekaibot.bot import Bot

__all__ = [
    "Rule",
    "RuleChecker",
    "MatchRule"
]


class Rule:
    """{ref}`nonebot.matcher.Matcher` 规则类。

    当事件传递时，在 {ref}`nonebot.matcher.Matcher` 运行前进行检查。

    参数:
        *checkers: RuleChecker

    用法:
        ```python
        Rule(async_function) & sync_function
        # 等价于
        Rule(async_function, sync_function)
        ```
    """

    __slots__ = ("checkers",)

    def __init__(self, *checkers: "Rule" | RuleCheckerT | Dependency[bool]) -> None:
        self.checkers: set[Dependency[bool]] = set(chain.from_iterable(
            checker.checkers if isinstance(checker, Rule) else {checker}
            for checker in checkers
        ))
        """存储 `RuleChecker`"""

    def __repr__(self) -> str:
        return f"Rule({', '.join(repr(checker) for checker in self.checkers)})"

    async def __call__(
        self,
        bot: "Bot",
        event: Event,
        state: StateT,
        global_state: GlobalStateT ,
        stack: AsyncExitStack | None = None,
        dependency_cache: dict[Dependency[Any], Any] | None = None,
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

class RuleChecker(ABC, Generic[ArgsT, ParamT]):
    """抽象基类，匹配消息规则。"""

    def __init__(self, rule: Rule) -> None:
        self.__rule__ = rule

    def __call__(self, cls: NodeT) -> NodeT:
        """将检查器添加到 Node 类中。"""
        if not isinstance(cls, type):
            raise TypeError(f"class should be NodeT, not `{type(cls)}`.")
        if not hasattr(cls, "__node_rule__"):
            setattr(cls, "__node_rule__", Rule())
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
        global_state: GlobalStateT ,
        stack: AsyncExitStack | None = None,
        dependency_cache: dict[Dependency[Any], Any] | None = None,
    ) -> bool:
        """直接运行检查器并获取结果。"""
        return await self.__rule__(bot, event, state, global_state, stack, dependency_cache)

    @classmethod
    @abstractmethod
    def _param(cls) -> ParamT:
        """获取规则参数，子类需实现。"""
        pass

    @final
    @classmethod
    def Param(cls) -> ParamT:
        """在依赖注入里获取检查器的数据。"""
        return Depends(cls._param, use_cache=False)
    
class MatchRule(RuleChecker[str | bool, str]):
    """所有匹配类 Rule 的基类。"""

    checker: Type[Callable[[tuple[str, ...], bool], "Rule"]] = None

    def __init__(
        self,
        *msgs: str | tuple[str, ...], 
        ignorecase: bool = False
    ) -> None:

        if self.checker is None:
            raise NotImplementedError(f"Subclasses of MatchRule must provide a checker.")

        super().__init__(Rule(self.checker(*msgs, ignorecase))) 

    @classmethod
    def Checker(
        cls,
        *msgs: str | tuple[str, ...], 
        ignorecase: bool = False
    ):
        return super().Checker(*msgs, ignorecase) 