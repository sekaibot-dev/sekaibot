"""SekaiBot 规则控制"""

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, overload
from typing_extensions import override

from sekaibot.consts import (
    CMD_ARG_KEY,
    CMD_KEY,
    CMD_START_KEY,
    CMD_WHITESPACE_KEY,
    COUNTER_LATEST_TIGGERS,
    COUNTER_TIME_TIGGERS,
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
from sekaibot.dependencies import Depends
from sekaibot.internal.event import Event
from sekaibot.internal.message import Message, MessageSegment
from sekaibot.internal.rule import Rule, RuleChecker
from sekaibot.internal.rule.utils import (
    ArgumentParser,
    CommandRule,
    CountTriggerRule,
    EndswithRule,
    FullmatchRule,
    KeywordsRule,
    RegexRule,
    ShellCommandRule,
    StartswithRule,
    ToMeRule,
    WordFilterRule,
)
from sekaibot.typing import StateT

__all__ = [
    "Command",
    "EndsWith",
    "FullMatch",
    "Keywords",
    "Regex",
    "Rule",
    "RuleChecker",
    "ShellCommand",
    "StartsWith",
    "ToMe",
]


class StartsWith(RuleChecker):
    """匹配消息富文本开头。"""

    def __init__(
        self, *msgs: str | MessageSegment[Any], ignorecase: bool = False
    ) -> None:
        """匹配消息富文本开头。

        Args:
            msgs: 指定消息开头字符串或 MessageSegment 元组
            ignorecase: 是否忽略大小写
        """
        super().__init__(Rule(StartswithRule(msgs, ignorecase=ignorecase)))

    @override
    @classmethod
    def Checker(
        cls, *msgs: str | MessageSegment[Any], ignorecase: bool = False
    ) -> bool:
        """匹配消息富文本开头。

        Args:
            msgs: 指定消息开头字符串或 MessageSegment 元组
            ignorecase: 是否忽略大小写
        """
        return super().Checker(msgs, ignorecase=ignorecase)

    @staticmethod
    def _param(state: StateT) -> Any:
        return state[STARTSWITH_KEY]

    @classmethod
    def Param(cls) -> str | MessageSegment[Any]:
        """在依赖注入里获取检查器的数据。"""
        return Depends(cls._param, use_cache=False)


class EndsWith(RuleChecker):
    """匹配消息富文本结尾。"""

    def __init__(
        self, *msgs: str | MessageSegment[Any], ignorecase: bool = False
    ) -> None:
        """匹配消息富文本结尾。

        Args:
            msgs: 指定消息结尾字符串或 MessageSegment 元组
            ignorecase: 是否忽略大小写
        """
        super().__init__(Rule(EndswithRule(msgs, ignorecase=ignorecase)))

    @override
    @classmethod
    def Checker(
        cls, *msgs: str | MessageSegment[Any], ignorecase: bool = False
    ) -> bool:
        """匹配消息富文本结尾。

        Args:
            msgs: 指定消息结尾字符串或 MessageSegment 元组
            ignorecase: 是否忽略大小写
        """
        return super().Checker(msgs, ignorecase=ignorecase)

    @staticmethod
    def _param(state: StateT) -> Any:
        return state[ENDSWITH_KEY]

    @classmethod
    def Param(cls) -> str | MessageSegment[Any]:
        """在依赖注入里获取检查器的数据。"""
        return Depends(cls._param, use_cache=False)


class FullMatch(RuleChecker):
    """完全匹配消息。"""

    def __init__(
        self, *msgs: str | Message[Any] | MessageSegment[Any], ignorecase: bool = False
    ) -> None:
        """完全匹配消息。

        Args:
            msgs: 指定消息全匹配字符串或 Message 或 MessageSegment 元组
            ignorecase: 是否忽略大小写
        """
        super().__init__(Rule(FullmatchRule(msgs, ignorecase=ignorecase)))

    @override
    @classmethod
    def Checker(
        cls, *msgs: str | Message[Any] | MessageSegment[Any], ignorecase: bool = False
    ) -> bool:
        """完全匹配消息。

        Args:
            msgs: 指定消息全匹配字符串或 Message 或 MessageSegment 元组
            ignorecase: 是否忽略大小写
        """
        return super().Checker(msgs, ignorecase=ignorecase)

    @staticmethod
    def _param(state: StateT) -> Any:
        return state[FULLMATCH_KEY]

    @classmethod
    def Param(cls) -> str | Message[Any]:
        """在依赖注入里获取检查器的数据。"""
        return Depends(cls._param, use_cache=False)


class Keywords(RuleChecker):
    """匹配消息富文本关键词。"""

    def __init__(
        self, *keywords: str | MessageSegment[Any], ignorecase: bool = False
    ) -> None:
        """匹配消息富文本关键词。

        Args:
            keywords: 指定关键字元组
            ignorecase: 是否忽略大小写
        """
        super().__init__(Rule(KeywordsRule(keywords, ignorecase=ignorecase)))

    @override
    @classmethod
    def Checker(
        cls, *keywords: str | MessageSegment[Any], ignorecase: bool = False
    ) -> bool:
        """匹配消息富文本关键词。

        Args:
            keywords: 指定关键字元组
            ignorecase: 是否忽略大小写
        """
        return super().Checker(keywords, ignorecase=ignorecase)

    @staticmethod
    def _param(state: StateT) -> Any:
        return state[KEYWORD_KEY]

    @classmethod
    def Param(cls) -> tuple[str | MessageSegment[Any], ...]:
        """在依赖注入里获取检查器的数据。"""
        return Depends(cls._param, use_cache=False)


class WordFilter(RuleChecker):
    """检查消息纯文本是不包含指定关键字，用于敏感词过滤。"""

    def __init__(
        self,
        *words: str,
        word_file: Path | None = None,
        ignorecase: bool = False,
        use_pinyin: bool = False,
        use_aho: bool = False,
    ) -> None:
        """匹配消息富文本关键词。

        Args:
            words: 指定关键字集合
            word_file: 可选的词库文件路径 (每行一个词)
            ignorecase: 是否忽略大小写
            use_pinyin: 是否启用拼音匹配，使用 `pypinyin` 库
            use_aho: 是否启用 Aho-Corasick 算法 (当词数较大时自动激活) ，使用 `pyahocorasick` 库
        """
        super().__init__(
            Rule(
                WordFilterRule(
                    word_file=word_file,
                    words=words,
                    ignorecase=ignorecase,
                    use_pinyin=use_pinyin,
                    use_aho=use_aho,
                )
            )
        )

    @override
    @classmethod
    def Checker(
        cls,
        *words: str,
        word_file: str | None = None,
        ignorecase: bool = False,
        use_pinyin: bool = False,
        use_aho: bool = False,
    ) -> bool:
        """匹配消息富文本关键词。

        Args:
            words: 指定关键字集合
            word_file: 可选的词库文件路径 (每行一个词)
            ignorecase: 是否忽略大小写
            use_pinyin: 是否启用拼音匹配，使用 `pypinyin` 库
            use_aho: 是否启用 Aho-Corasick 算法 (当词数较大时自动激活) ，使用 `pyahocorasick` 库
        """
        return super().Checker(
            word_file=word_file,
            words=words,
            ignorecase=ignorecase,
            use_pinyin=use_pinyin,
            use_aho=use_aho,
        )


class Regex(RuleChecker):
    """匹配符合正则表达式的消息字符串。

    Depends:
        {ref}`sekaibot.rule.Regex.RegexStr`: 获取匹配成功的字符串。
        {ref}`sekaibot.rule.Regex.RegexGroup`: 获取匹配成功的 group 元组。
        {ref}`sekaibot.rule.Regex.RegexDict`: 获取匹配成功的 group 字典。

    Args:
        regex: 正则表达式
        flags: 正则表达式标记

    Tip:
        正则表达式匹配使用 search 而非 match，如需从头匹配请使用 `r"^xxx"` 来确保匹配开头
        正则表达式匹配使用 `EventMessage` 的 `str` 字符串，
        而非 `EventMessage` 的 `PlainText` 纯文本字符串。
    """

    def __init__(self, regex: str, flags: int | re.RegexFlag = 0) -> None:
        """匹配符合正则表达式的消息字符串。

        Args:
            regex: 正则表达式
            flags: 正则表达式标记
        """
        super().__init__(Rule(RegexRule(regex, flags)))

    @override
    @classmethod
    def Checker(cls, regex: str, flags: int | re.RegexFlag = 0) -> bool:
        """匹配符合正则表达式的消息字符串。

        Args:
            regex: 正则表达式
            flags: 正则表达式标记
        """
        return super().Checker(regex, flags)

    @staticmethod
    def _regex_matched(state: StateT) -> Any:
        return state[REGEX_MATCHED]

    @classmethod
    def RegexMatched(cls) -> re.Match[str]:
        """正则匹配结果"""
        return Depends(cls._regex_matched, use_cache=False)

    @classmethod
    def _regex_str(
        cls,
        groups: tuple[str | int, ...],
    ) -> Callable[[StateT], str | tuple[str | Any, ...] | Any]:
        def _regex_str_dependency(
            state: StateT,
        ) -> str | tuple[str | Any, ...] | Any:
            return cls._regex_matched(state).group(*groups)

        return _regex_str_dependency

    @overload
    @classmethod
    def RegexStr(cls, group: Literal[0] = 0, /) -> str: ...

    @overload
    @classmethod
    def RegexStr(cls, group: str | int, /) -> str | Any: ...

    @overload
    @classmethod
    def RegexStr(
        cls, group1: str | int, group2: str | int, /, *groups: str | int
    ) -> tuple[str | Any, ...]: ...

    @classmethod
    def RegexStr(cls, *groups: str | int) -> str | tuple[str | Any, ...] | Any:
        """正则匹配结果文本"""
        return Depends(cls._regex_str(groups), use_cache=False)

    @classmethod
    def _regex_group(cls) -> Callable[[StateT], tuple[Any, ...]]:
        def _regex_group_dependency(
            state: StateT,
        ) -> tuple[Any, ...]:
            return cls._regex_matched(state).groups()

        return _regex_group_dependency

    @classmethod
    def RegexGroup(cls) -> tuple[Any, ...]:
        """正则匹配结果 group 元组"""
        return Depends(cls._regex_group(), use_cache=False)

    @classmethod
    def _regex_dict(cls) -> Callable[[StateT], dict[str, Any]]:
        def _regex_dict_dependency(state: StateT) -> dict[str, Any]:
            return cls._regex_matched(state).groupdict()

        return _regex_dict_dependency

    @classmethod
    def RegexDict(cls) -> dict[str, Any]:
        """正则匹配结果 group 字典"""
        return Depends(cls._regex_dict(), use_cache=False)


class CountTrigger(RuleChecker):
    """计数器规则。"""

    def __init__(
        self,
        min_trigger: int = 10,
        time_window: int = 60,
        count_window: int = 30,
        max_size: int | None = 100,
        rule: Rule | None = None,
    ) -> None:
        """计数器规则。

        Args:
            min_trigger (int): 触发次数
            time_window (int): 时间窗口 (秒)
            count_window (int): 计数窗口 (秒)
            max_size (int): 最大缓存大小
            rule (Rule): 触发计数器需要满足的 Rule
        """
        super().__init__(
            Rule(
                CountTriggerRule(
                    time_window=time_window,
                    count_window=count_window,
                    min_trigger=min_trigger,
                    max_size=max_size,
                    rule=rule,
                )
            )
        )

    @override
    @classmethod
    def Checker(
        cls,
        min_trigger: int = 10,
        time_window: int = 60,
        count_window: int = 30,
        max_size: int | None = 100,
        rule: Rule | None = None,
    ) -> bool:
        """计数器规则。

        Args:
            min_trigger (int): 触发次数
            time_window (int): 时间窗口 (秒)
            count_window (int): 计数窗口 (秒)
            max_size (int): 最大缓存大小
            rule (Rule): 触发计数器需要满足的 Rule
        """
        return super().Checker(
            time_window=time_window,
            count_window=count_window,
            min_trigger=min_trigger,
            max_size=max_size,
            rule=rule,
        )

    @staticmethod
    def _time_trigger(state: StateT) -> Any:
        return state[COUNTER_TIME_TIGGERS]

    @classmethod
    def TimeTrigger(cls) -> tuple[Event[Any], ...]:
        """在依赖注入里获取检查器的数据。"""
        return Depends(cls._time_trigger, use_cache=False)

    @staticmethod
    def _latest_trigger(state: StateT) -> Any:
        return state[COUNTER_LATEST_TIGGERS]

    @classmethod
    def LatestTrigger(cls) -> tuple[Event[Any], ...]:
        """在依赖注入里获取检查器的数据。"""
        return Depends(cls._latest_trigger, use_cache=False)


class Command(RuleChecker):
    """匹配消息命令。

    Config:
        `{ref}sekaibot.config.MainConfig.rule.command_start`
        `{ref}sekaibot.config.MainConfig.rule.command_sep`

    Depends:
        `{ref}sekaibot.rule.Command.Command`: 获取匹配成功的命令元组 (如: `("test",)`)
        `{ref}sekaibot.rule.Command.RawCommand`: 获取原始命令文本 (如: `"/test"`)
        `{ref}sekaibot.rule.Command.CommandArg`: 获取匹配成功的命令参数字符串

    Tip:
        命令内容与后续消息之间无需空格！

    Examples:
        使用默认配置 `command_start`, `command_sep` 时:

        - 命令 `("test",)` 可以匹配以 `/test` 开头的消息
        - 命令 `("test", "sub")` 可以匹配以 `/test.sub` 开头的消息
    """

    def __init__(
        self, *cmds: tuple[str, ...], force_whitespace: str | bool | None = None
    ) -> None:
        """匹配消息命令。

        Args:
            cmds (str | tuple[str, ...]): 命令文本或命令元组。
            force_whitespace (bool): 是否强制命令后必须有空白符 (如空格、换行等) 。
        """
        super().__init__(Rule(CommandRule(cmds, force_whitespace=force_whitespace)))

    @override
    @classmethod
    def Checker(
        cls, *cmds: tuple[str, ...], force_whitespace: str | bool | None = None
    ) -> bool:
        """匹配消息命令。

        Args:
            cmds (str | tuple[str, ...]): 命令文本或命令元组。
            force_whitespace (bool): 是否强制命令后必须有空白符 (如空格、换行等) 。
        """
        return super().Checker(cmds, force_whitespace=force_whitespace)

    @staticmethod
    def _command(state: StateT) -> Any:
        return state[PREFIX_KEY][CMD_KEY]

    @classmethod
    def Command(cls) -> tuple[str, ...]:
        """消息命令元组"""
        return Depends(cls._command, use_cache=False)

    @staticmethod
    def _raw_command(state: StateT) -> Any:
        return state[PREFIX_KEY][RAW_CMD_KEY]

    @classmethod
    def RawCommand(cls) -> str:
        """消息命令文本"""
        return Depends(cls._raw_command, use_cache=False)

    @staticmethod
    def _command_arg(state: StateT) -> Any:
        return state[PREFIX_KEY][CMD_ARG_KEY]

    @classmethod
    def CommandArg(cls) -> Any:
        """消息命令参数"""
        return Depends(cls._command_arg, use_cache=False)

    @staticmethod
    def _command_start(state: StateT) -> Any:
        return state[PREFIX_KEY][CMD_START_KEY]

    @classmethod
    def CommandStart(cls) -> str:
        """消息命令开头"""
        return Depends(cls._command_start, use_cache=False)

    @staticmethod
    def _command_whitespace(state: StateT) -> Any:
        return state[PREFIX_KEY][CMD_WHITESPACE_KEY]

    @classmethod
    def CommandWhitespace(cls) -> str:
        """消息命令与参数之间的空白"""
        return Depends(cls._command_whitespace, use_cache=False)


class ShellCommand(Command):
    """匹配 `shell_like` 形式的消息命令。

    Config:
    - `{ref}sekaibot.config.MainConfig.rule.command_start`
    - `{ref}sekaibot.config.MainConfig.rule.command_sep`

    Depends:
    - `{ref}sekaibot.rule.ShellCommand.Command`: 匹配成功的命令元组 (例如: `("test",)`)
    - `{ref}sekaibot.rule.ShellCommand.RawCommand`: 原始命令文本 (例如: `"/test"`)
    - `{ref}sekaibot.rule.ShellCommand.ShellCommandArgv`: 解析前的参数列表 (例如: `["arg", "-h"]`)
    - `{ref}sekaibot.rule.ShellCommand.ShellCommandArgs`: 解析后的参数字典 (例如: `{"arg": "arg", "h": True}`)

    Warnings:
        如果参数解析失败，通过 `{ref}sekaibot.rule.ShellCommandArgs` 获取的将是
        `{ref}sekaibot.exceptions.ParserExit` 异常对象。

    Tips:
        命令内容与后续消息之间无需空格！

    Examples:
        使用默认的 `command_start` 和 `command_sep` 配置:

        ```python
        from sekaibot.rule import ArgumentParser

        parser = ArgumentParser()
        parser.add_argument("-a", action="store_true")

        rule = shell_command("ls", parser=parser)
        ```
    """

    def __init__(
        self, *cmds: tuple[str, ...], parser: ArgumentParser | None = None
    ) -> None:
        """匹配 `shell_like` 形式的消息命令。

        Args:
            cmds (str | tuple[str, ...]): 命令文本或命令元组。
            parser (ArgumentParser | None): 可选的 `{ref}sekaibot.rule.ArgumentParser` 对象。
        """
        super(Command, self).__init__(Rule(ShellCommandRule(cmds, parser=parser)))

    @override
    @classmethod
    def Checker(  # type: ignore
        cls, *cmds: tuple[str, ...], parser: ArgumentParser | None = None
    ) -> bool:
        """匹配 `shell_like` 形式的消息命令。

        Args:
            cmds (str | tuple[str, ...]): 命令文本或命令元组。
            parser (ArgumentParser | None): 可选的 `{ref}sekaibot.rule.ArgumentParser` 对象。
        """
        return super(Command, cls).Checker(*cmds, parser=parser)

    @staticmethod
    def _shell_command_args(state: StateT) -> Any:
        return state[SHELL_ARGS]  # Namespace or ParserExit

    @classmethod
    def ShellCommandArgs(cls) -> Any:
        """Shell 命令解析后的参数字典"""
        return Depends(cls._shell_command_args, use_cache=False)

    @staticmethod
    def _shell_command_argv(state: StateT) -> Any:
        return state[SHELL_ARGV]

    @classmethod
    def ShellCommandArgv(cls) -> list[str | MessageSegment[Any]]:
        """Shell 命令原始参数列表"""
        return Depends(cls._shell_command_argv, use_cache=False)


class ToMe(RuleChecker):
    """匹配与机器人有关的事件。"""

    def __init__(self) -> None:
        super().__init__(Rule(ToMeRule()))

    @override
    @classmethod
    def Checker(cls) -> bool:
        """匹配与机器人有关的事件。"""
        return super().Checker()

    @staticmethod
    def _param(event: Event[Any]) -> bool:
        return event.is_tome()

    @classmethod
    def Param(cls) -> bool:
        """在依赖注入里获取检查器的数据。"""
        return Depends(cls._param, use_cache=False)
