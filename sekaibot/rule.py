import re
from typing import Any

from sekaibot.consts import (
    COUNTER_INFO,
    ENDSWITH_KEY,
    FULLMATCH_KEY,
    KEYWORD_KEY,
    REGEX_MATCHED,
    STARTSWITH_KEY,
)
from sekaibot.dependencies import Dependency
from sekaibot.internal.event import Event
from sekaibot.internal.rule import MatchRule, Rule, RuleChecker
from sekaibot.internal.rule.utils import (
    CountTriggerRule,
    EndswithRule,
    FullmatchRule,
    KeywordsRule,
    # CommandRule,
    # ShellCommandRule,
    RegexRule,
    StartswithRule,
    ToMeRule,
)
from sekaibot.typing import StateT

__all__ = [
    "StartsWith",
    "EndsWith",
    "FullMatch",
    "Keywords",
    # "Command",
    # "ShellCommand",
    "Regex",
    "ToMe",
]


class StartsWith(MatchRule):
    """匹配消息纯文本开头。

    参数:
        msg: 指定消息开头字符串元组
        ignorecase: 是否忽略大小写
    """

    __slots__ = ("__rule__", "checker")

    checker = StartswithRule

    @classmethod
    def _param(cls, state: StateT):
        return state[STARTSWITH_KEY]


class EndsWith(MatchRule):
    """匹配消息纯文本结尾。

    参数:
        msg: 指定消息开头字符串元组
        ignorecase: 是否忽略大小写
    """

    __slots__ = ("__rule__", "checker")

    checker = EndswithRule

    @classmethod
    def _param(cls, state: StateT):
        return state[ENDSWITH_KEY]


class FullMatch(MatchRule):
    """完全匹配消息。

    参数:
        msg: 指定消息全匹配字符串元组
        ignorecase: 是否忽略大小写
    """

    __slots__ = ("__rule__", "checker")

    checker = FullmatchRule

    @classmethod
    def _param(cls, state: StateT):
        return state[FULLMATCH_KEY]


class Keywords(RuleChecker[tuple[list[str], bool], tuple[str, ...]]):
    """匹配消息纯文本关键词。

    参数:
        keywords: 指定关键字元组
    """

    __slots__ = ("__rule__",)

    def __init__(self, *keywords: str, ignorecase: bool = False) -> None:
        super().__init__(KeywordsRule(*keywords, ignorecase))

    @classmethod
    def Checker(cls, *keywords: str, ignorecase: bool = False):
        return super().Checker(*keywords, ignorecase)

    @classmethod
    def _param(cls, state: StateT):
        return state[KEYWORD_KEY]


class Regex(RuleChecker[tuple[str, re.RegexFlag], re.Match[str]]):
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

    __slots__ = ("__rule__",)

    def __init__(self, regex: str, flags: int | re.RegexFlag = 0) -> Rule:
        super().__init__(RegexRule(regex, flags))

    @classmethod
    def Checker(cls, regex: str, flags: int | re.RegexFlag = 0):
        return super().Checker(regex, flags)

    @classmethod
    def _param(cls, state: StateT):
        return state[REGEX_MATCHED]


class CountTrigger(RuleChecker[tuple[str, Dependency[bool], int, int, int, int], dict]):
    """计数器规则。

    参数:
        name: 计数器名称
        times: 计数器次数
    """

    __slots__ = ("__rule__",)

    def __init__(
        self,
        name: str,
        func: Dependency[bool] | None = None,
        min_trigger: int = 10,
        time_window: int = 60,
        count_window: int = 30,
        max_size: int | None = 100,
    ) -> Rule:
        super().__init__(
            CountTriggerRule(name, func, min_trigger, time_window, count_window, max_size)
        )

    @classmethod
    def Checker(
        cls,
        name: str,
        func: Dependency[bool] | None = None,
        min_trigger: int = 10,
        time_window: int = 60,
        count_window: int = 30,
        max_size: int | None = 100,
    ):
        return super().Checker(name, name, func, min_trigger, time_window, count_window, max_size)

    @classmethod
    def _param(cls, state: StateT):
        return state[COUNTER_INFO]


class ToMe(RuleChecker[Any, bool]):
    """匹配与机器人有关的事件。"""

    __slots__ = ("__rule__",)

    def __init__(self) -> None:
        super().__init__(ToMeRule())

    @classmethod
    def Checker(cls):
        return super().Checker()

    @classmethod
    def _param(cls, event: Event) -> bool:
        return event.is_tome()
