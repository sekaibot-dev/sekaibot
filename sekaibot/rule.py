from typing import (
    Union,
    Callable,
    Self
)
import re

from sekaibot.internal.event import Event
from sekaibot.typing import NodeT, RuleCheckerT
from sekaibot.dependencies import Dependency
from sekaibot.internal.rule import Rule
from sekaibot.internal.rule.utils import (
    StartswithRule,
    EndswithRule,
    FullmatchRule,
    KeywordsRule,
    #CommandRule,
    #ShellCommandRule,
    RegexRule,
    ToMeRule,
)

__all__ = [
    "rule"
]


class rule:
    """一个装饰器，可以将一个 Node 类中的消息规则添加到 Node 类中。"""

    def __init__(self, *rule: Rule | RuleCheckerT | Dependency[bool]) -> None:
        self.rule = Rule(*rule)

    def __call__(self, cls: NodeT) -> NodeT:
        if not isinstance(cls, type):
            raise TypeError(f"class should be NodeT, not `{type(cls)}`.")
        if not hasattr(cls, "__node_rule_func__"):
            setattr(cls, "__node_rule_func__", Rule())
        cls.__node_rule__ += self.rule
        return cls


def startswith(
    msg: Union[str, tuple[str, ...]], ignorecase: bool = False
) -> Callable[[NodeT], NodeT]:
    """匹配消息纯文本开头。

    参数:
        msg: 指定消息开头字符串元组
        ignorecase: 是否忽略大小写
    """
    
    if isinstance(msg, str):
        msg = (msg,)

    return Rule(StartswithRule(msg, ignorecase))

@staticmethod
def endswith( 
    msg: Union[str, tuple[str, ...]], ignorecase: bool = False
) -> Callable[[NodeT], NodeT]:
    """匹配消息纯文本结尾。

    参数:
        msg: 指定消息开头字符串元组
        ignorecase: 是否忽略大小写
    """

    if isinstance(msg, str):
        msg = (msg,)

    return Rule(EndswithRule(msg, ignorecase))


@staticmethod
def fullmatch(
    msg: Union[str, tuple[str, ...]], ignorecase: bool = False
) -> Callable[[NodeT], NodeT]:
    """完全匹配消息。

    参数:
        msg: 指定消息全匹配字符串元组
        ignorecase: 是否忽略大小写
    """

    if isinstance(msg, str):
        msg = (msg,)

    return Rule(FullmatchRule(msg, ignorecase))


@staticmethod
def keyword(
    *keywords: str
) -> Callable[[NodeT], NodeT]:
    """匹配消息纯文本关键词。

    参数:
        keywords: 指定关键字元组
    """

    return Rule(KeywordsRule(*keywords))


@staticmethod
def regex(
    regex: str, flags: Union[int, re.RegexFlag] = 0
) -> Callable[[NodeT], NodeT]:
    """匹配符合正则表达式的消息字符串。

    可以通过 {ref}`nonebot.params.RegexStr` 获取匹配成功的字符串，
    通过 {ref}`nonebot.params.RegexGroup` 获取匹配成功的 group 元组，
    通过 {ref}`nonebot.params.RegexDict` 获取匹配成功的 group 字典。

    参数:
        regex: 正则表达式
        flags: 正则表达式标记

    :::tip 提示
    正则表达式匹配使用 search 而非 match，如需从头匹配请使用 `r"^xxx"` 来确保匹配开头
    :::

    :::tip 提示
    正则表达式匹配使用 `EventMessage` 的 `str` 字符串，
    而非 `EventMessage` 的 `PlainText` 纯文本字符串
    :::
    """
    
    return Rule(RegexRule(regex, flags))


@staticmethod
def to_me() -> Callable[[NodeT], NodeT]:
    """匹配与机器人有关的事件。"""

    return Rule(ToMeRule())