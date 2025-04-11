import re
from typing import Any

from sekaibot.consts import (
    CMD_ARG_KEY,
    CMD_KEY,
    CMD_START_KEY,
    CMD_WHITESPACE_KEY,
    COUNTER_KEY,
    ENDSWITH_KEY,
    FULLMATCH_KEY,
    KEYWORD_KEY,
    PREFIX_KEY,
    RAW_CMD_KEY,
    REGEX_MATCHED,
    SHELL_ARGS,
    SHELL_ARGV,
    STARTSWITH_KEY,
)
from sekaibot.dependencies import Dependency, Depends
from sekaibot.internal.event import Event
from sekaibot.internal.message import Message, MessageSegment
from sekaibot.internal.rule import MatchRule, Rule, RuleChecker
from sekaibot.internal.rule.utils import (  # CommandRule,; ShellCommandRule,
    CountTriggerRule,
    EndswithRule,
    FullmatchRule,
    KeywordsRule,
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

    Args:
        msg: 指定消息开头字符串元组
        ignorecase: 是否忽略大小写
    """

    checker = StartswithRule

    @staticmethod
    def _param(state: StateT):
        return state[STARTSWITH_KEY]


class EndsWith(MatchRule):
    """匹配消息纯文本结尾。

    Args:
        msg: 指定消息开头字符串元组
        ignorecase: 是否忽略大小写
    """

    checker = EndswithRule

    @staticmethod
    def _param(state: StateT):
        return state[ENDSWITH_KEY]


class FullMatch(MatchRule):
    """完全匹配消息。

    Args:
        msg: 指定消息全匹配字符串元组
        ignorecase: 是否忽略大小写
    """

    checker = FullmatchRule

    @staticmethod
    def _param(state: StateT):
        return state[FULLMATCH_KEY]


class Keywords(RuleChecker[tuple[tuple[str, ...], bool], tuple[str, ...]]):
    """匹配消息纯文本关键词。

    Args:
        keywords: 指定关键字元组
    """

    def __init__(self, *keywords: str, ignorecase: bool = False) -> None:
        super().__init__(KeywordsRule(*keywords, ignorecase=ignorecase))

    @classmethod
    def Checker(cls, *keywords: str, ignorecase: bool = False):
        return super().Checker(*keywords, ignorecase=ignorecase)

    @staticmethod
    def _param(state: StateT):
        return state[KEYWORD_KEY]


class Regex(RuleChecker[tuple[str, re.RegexFlag], re.Match[str]]):
    """匹配符合正则表达式的消息字符串。

    可以通过 {ref}`nonebot.params.RegexStr` 获取匹配成功的字符串，
    通过 {ref}`nonebot.params.RegexGroup` 获取匹配成功的 group 元组，
    通过 {ref}`nonebot.params.RegexDict` 获取匹配成功的 group 字典。

    Args:
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

    def __init__(self, regex: str, flags: int | re.RegexFlag = 0) -> Rule:
        super().__init__(RegexRule(regex, flags))

    @classmethod
    def Checker(cls, regex: str, flags: int | re.RegexFlag = 0):
        return super().Checker(regex, flags)

    @staticmethod
    def _param(state: StateT):
        return state[REGEX_MATCHED]


class CountTrigger(RuleChecker[tuple[str, Dependency[bool], int, int, int, int], dict]):
    """计数器规则。

    Args:
        name: 计数器名称
        times: 计数器次数
    """

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

    @staticmethod
    def _param(state: StateT):
        return state[COUNTER_KEY]


def _command(state: StateT) -> Message:
    return state[PREFIX_KEY][CMD_KEY]


def Command() -> tuple[str, ...]:
    """消息命令元组"""
    return Depends(_command)


def _raw_command(state: StateT) -> Message:
    return state[PREFIX_KEY][RAW_CMD_KEY]


def RawCommand() -> str:
    """消息命令文本"""
    return Depends(_raw_command)


def _command_arg(state: StateT) -> Message:
    return state[PREFIX_KEY][CMD_ARG_KEY]


def CommandArg() -> Any:
    """消息命令参数"""
    return Depends(_command_arg)


def _command_start(state: StateT) -> str:
    return state[PREFIX_KEY][CMD_START_KEY]


def CommandStart() -> str:
    """消息命令开头"""
    return Depends(_command_start)


def _command_whitespace(state: StateT) -> str:
    return state[PREFIX_KEY][CMD_WHITESPACE_KEY]


def CommandWhitespace() -> str:
    """消息命令与参数之间的空白"""
    return Depends(_command_whitespace)


def _shell_command_args(state: StateT) -> Any:
    return state[SHELL_ARGS]  # Namespace or ParserExit


def ShellCommandArgs() -> Any:
    """shell 命令解析后的参数字典"""
    return Depends(_shell_command_args, use_cache=False)


def _shell_command_argv(state: StateT) -> list[str | MessageSegment]:
    return state[SHELL_ARGV]


def ShellCommandArgv() -> Any:
    """shell 命令原始参数列表"""
    return Depends(_shell_command_argv, use_cache=False)


class ToMe(RuleChecker[Any, bool]):
    """匹配与机器人有关的事件。"""

    def __init__(self) -> None:
        super().__init__(ToMeRule())

    @classmethod
    def Checker(cls):
        return super().Checker()

    @staticmethod
    def _param(event: Event) -> bool:
        return event.is_tome()
