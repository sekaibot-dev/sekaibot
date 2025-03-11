from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, NoReturn, Optional, Union, Dict, Any, Self

import anyio
from exceptiongroup import BaseExceptionGroup, catch

from sekaibot.dependencies import Dependency, InnerDepends, Depends, solve_dependencies_in_bot
from sekaibot.exceptions import SkipException
from sekaibot.internal.event import Event
from sekaibot.typing import RuleCheckerT, StateT

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

    def __init__(self, *checkers: Union[RuleCheckerT, Dependency[bool]]) -> None:
        self.checkers: set[Dependency[bool]] = {
            (
                checker
                if isinstance(checker, InnerDepends)
                else Depends(checker) 
            )
            for checker in checkers
        }
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
                state=state,
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
            return Rule(other, *self.checkers)
        
    def __iadd__(self, other: Union[Self, RuleCheckerT]) -> Self:
        return self.__add__(other)
    
    def __sub__(self, other: Union[Self, RuleCheckerT]) -> NoReturn:
        raise RuntimeError("Subtraction operation between rules is not allowed.")