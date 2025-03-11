from typing import (
    Union,
)
from functools import wraps
import inspect

from sekaibot.typing import EventT, NodeT, RuleCheckerT
from sekaibot.dependencies import Dependency
from sekaibot.utils import wrap_get_func
from sekaibot.internal.rule import Rule

"""
NodeT = TypeVar("NodeT", bound="Node")
RuleCheckerT = Callable[["Bot", "Event[Any]", StateT], Union[bool, Awaitable[bool]]]
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
class Node(ABC, Generic[EventT, StateT, ConfigT]):
    __node_rule_func__: ClassVar[Rule] = Rule()
"""

def to_rule(func: Union[RuleCheckerT, Dependency[bool]]) -> Rule:
    return Rule(wrap_get_func(func))

def rule(
    cls: NodeT, 
    *,
    rule: Rule | RuleCheckerT | Dependency[bool]
) -> NodeT:
    if not isinstance(cls, type):
        raise TypeError(f"class should be NodeT, not `{type(cls)}`.")
    if not hasattr(cls, "__node_rule_func__"):
        setattr(cls, "__node_rule_func__", Rule())
    if isinstance(rule, Rule):
        cls.__node_rule_func__ += rule
    elif isinstance(rule, (Dependency, RuleCheckerT)):
        cls.__node_rule_func__ += to_rule(rule)
    else:
        raise TypeError(f"rule should be Rule, Dependency or RuleCheckerT, not `{type(rule).__name__}`.")
    return cls