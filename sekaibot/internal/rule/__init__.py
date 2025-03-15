from abc import ABC, abstractmethod
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, NoReturn, Optional, Union, Dict, Any, Self, Tuple

import anyio
from exceptiongroup import BaseExceptionGroup, catch

from sekaibot.dependencies import Dependency, InnerDepends, Depends, solve_dependencies_in_bot
from sekaibot.exceptions import SkipException
from sekaibot.internal.event import Event
from itertools import chain
from sekaibot.typing import RuleCheckerT, StateT, NodeT
from sekaibot.consts import NODE_RULE_STATE

if TYPE_CHECKING:
    from sekaibot.bot import Bot

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

    def __init__(self, *checkers: Union[Self,RuleCheckerT, Dependency[bool]]) -> None:
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
        stack: Optional[AsyncExitStack] = None,
        dependency_cache: Optional[Dict[Dependency[Any], Any]] = None,
    ) -> bool:
        """检查是否符合所有规则

        参数:
            bot: Bot 对象
            event: Event 对象
            state: 当前 State
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
                state=state[NODE_RULE_STATE],
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

    def __and__(self, other: Optional[Union[Self, RuleCheckerT]]) -> Self:
        if other is None:
            return self
        elif isinstance(other, Rule):
            return Rule(*self.checkers, *other.checkers)
        else:
            return Rule(*self.checkers, other)

    def __rand__(self, other: Optional[Union[Self, RuleCheckerT]]) -> Self:
        if other is None:
            return self
        elif isinstance(other, Rule):
            return Rule(*other.checkers, *self.checkers)
        else:
            return Rule(other, *self.checkers)

    def __or__(self, other: object) -> NoReturn:
        raise RuntimeError("Or operation between rules is not allowed.")
    
    def __add__(self, other: Union[Self, RuleCheckerT]) -> Self:
        if other is None:
            return self
        elif isinstance(other, Rule):
            return Rule(*self.checkers, *other.checkers)
        else:
            return Rule(*self.checkers, other)
        
    def __iadd__(self, other: Union[Self, RuleCheckerT]) -> Self:
        return self.__add__(other)
    
    def __sub__(self, other: Union[Self, RuleCheckerT]) -> NoReturn:
        raise RuntimeError("Subtraction operation between rules is not allowed.")
    

class RuleChecker(ABC):
    """{ref}`nonebot.matcher.Matcher` 规则检查器。
    """
    __rule__: Rule = Rule()

    def __init__(self, rule: Rule | RuleCheckerT | Dependency) -> None:
        """注入rule。"""
        self.__rule__ = rule if isinstance(rule, Rule) else Rule(rule)

    def __call__(self, cls: NodeT) -> NodeT:
        """将检查器添加到 Node 类中。"""
        if not isinstance(cls, type):
            raise TypeError(f"class should be NodeT, not `{type(cls)}`.")
        if not hasattr(cls, "__node_rule_func__"):
            setattr(cls, "__node_rule_func__", Rule())
        cls.__node_rule__ += self.__rule__
        return cls
    
    async def check(
        self,
        bot: "Bot",
        event: Event,
        state: StateT,
    ):
        """直接运行检查器并获取结果。"""
        return await self.__rule__(bot, event, state, None, {})
    
    @abstractmethod
    def param(self) -> Any:
        """获取检查器的数据。"""

    def Param(self) -> InnerDepends:
        async def check_and_return_param(bot: "Bot", event: Event, state: StateT) -> Any:
            if not self.param():
                await self.check(bot, event, state)
            return self.param()
        return Depends(check_and_return_param, use_cache=False)