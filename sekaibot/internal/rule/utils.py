"""本模块是 {ref}`nonebot.matcher.Matcher.rule` 的类型定义。

每个{ref}`事件响应器 <nonebot.matcher.Matcher>`拥有一个
{ref}`nonebot.rule.Rule`，其中是 `RuleChecker` 的集合。
只有当所有 `RuleChecker` 检查结果为 `True` 时继续运行。

FrontMatter:
    mdx:
        format: md
    sidebar_position: 5
    description: nonebot.rule 模块
"""

from argparse import Action, ArgumentError
from argparse import ArgumentParser as ArgParser
from argparse import Namespace as Namespace
from collections.abc import Sequence
from contextvars import ContextVar
from gettext import gettext
from itertools import chain, product
from collections import deque
import time as time_util
import re
import shlex
from typing import (
    IO,
    TYPE_CHECKING,
    NamedTuple,
    Optional,
    TypedDict,
    TypeVar,
    Callable,
    Awaitable,
    Union,
    Self,
    cast,
    overload,
)

from pygtrie import CharTrie

from sekaibot.internal.event import Event
from sekaibot.internal.message import Message, MessageSegment, MessageT, MessageSegmentT
from sekaibot.consts import (
    STARTSWITH_KEY,
    ENDSWITH_KEY,
    FULLMATCH_KEY,
    KEYWORD_KEY,
    REGEX_MATCHED,
    COUNTER_INFO,
    COUNTER_STATE,
    PREFIX_KEY,
    RAW_CMD_KEY,
    CMD_ARG_KEY,
    CMD_KEY,
    CMD_START_KEY,
    CMD_WHITESPACE_KEY,
    SHELL_ARGS,
    SHELL_ARGV,
    
)

from . import Rule
from sekaibot.log import logger
from sekaibot.typing import NOT_GIVEN, EventT, _RuleStateT, _BotStateT
from sekaibot.dependencies import Dependency, solve_dependencies_in_bot

if TYPE_CHECKING:
    from sekaibot.bot import Bot

T = TypeVar("T")


class CMD_RESULT(TypedDict):
    command: Optional[tuple[str, ...]]
    raw_command: str | None
    command_arg: Optional[Message]
    command_start: str | None
    command_whitespace: str | None


class TRIE_VALUE(NamedTuple):
    command_start: str
    command: tuple[str, ...]


parser_message: ContextVar[str] = ContextVar("parser_message")


class StartswithRule:
    """检查消息纯文本是否以指定字符串开头。
        注意，此处仅匹配字符串，但是Message提供了匹配MessageSegment的方法，
        若需要请在rule函数中调用startswith方法。

    Args:
        msgs: 指定消息开头字符串元组
        ignorecase: 是否忽略大小写
    """

    __slots__ = ("ignorecase", "msgs")

    def __init__(self, *msgs: str, ignorecase: bool = False):
        self.msgs = msgs
        self.ignorecase = ignorecase

    def __repr__(self) -> str:
        return f"Startswith(msg={self.msgs}, ignorecase={self.ignorecase})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, StartswithRule)
            and frozenset(self.msgs) == frozenset(other.msgs)
            and self.ignorecase == other.ignorecase
        )

    def __hash__(self) -> int:
        return hash((frozenset(self.msgs), self.ignorecase))

    async def __call__(self, event: Event, rule_state: _RuleStateT) -> bool:
        try:
            message = event.get_message()
        except Exception:
            return False
        if match := message.startswith(
            self.msgs,
            ignorecase=self.ignorecase
        ):
            rule_state[STARTSWITH_KEY] = match
            return True
        return False


class EndswithRule:
    """检查消息纯文本是否以指定字符串结尾。
        注意，此处仅匹配字符串，但是Message提供了匹配MessageSegment的方法，
        若需要请在rule函数中调用endswith方法。

    Args:
        msgs: 指定消息结尾字符串元组
        ignorecase: 是否忽略大小写
    """

    __slots__ = ("ignorecase", "msgs")

    def __init__(self, *msgs: str, ignorecase: bool = False):
        self.msgs = msgs
        self.ignorecase = ignorecase

    def __repr__(self) -> str:
        return f"Endswith(msg={self.msgs}, ignorecase={self.ignorecase})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, EndswithRule)
            and frozenset(self.msgs) == frozenset(other.msgs)
            and self.ignorecase == other.ignorecase
        )

    def __hash__(self) -> int:
        return hash((frozenset(self.msgs), self.ignorecase))

    async def __call__(self, event: Event, rule_state: _RuleStateT) -> bool:
        try:
            message = event.get_message()
        except Exception:
            return False
        if match := message.endswith(
            self.msgs, 
            ignorecase=self.ignorecase
        ):
            rule_state[ENDSWITH_KEY] = match
            return True
        return False


class FullmatchRule:
    """检查消息纯文本是否与指定字符串全匹配。

    Args:
        msgs: 指定消息全匹配字符串元组
        ignorecase: 是否忽略大小写
    """

    __slots__ = ("ignorecase", "msgs")

    def __init__(self, *msgs: str, ignorecase: bool = False):
        self.msgs = tuple(map(str.casefold, msgs) if ignorecase else msgs)
        self.ignorecase = ignorecase

    def __repr__(self) -> str:
        return f"Fullmatch(msg={self.msgs}, ignorecase={self.ignorecase})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, FullmatchRule)
            and frozenset(self.msgs) == frozenset(other.msgs)
            and self.ignorecase == other.ignorecase
        )

    def __hash__(self) -> int:
        return hash((frozenset(self.msgs), self.ignorecase))

    async def __call__(self, event: Event, rule_state: _RuleStateT) -> bool:
        try:
            text = event.get_plain_text()
        except Exception:
            return False
        if not text:
            return False
        text = text.casefold() if self.ignorecase else text
        if text in self.msgs:
            rule_state[FULLMATCH_KEY] = text
            return True
        return False


class KeywordsRule:
    """检查消息纯文本是否包含指定关键字。

    Args:
        keywords: 指定关键字元组
    """

    __slots__ = ("ignorecase", "keywords")

    def __init__(self, *keywords: str, ignorecase: bool = False):
        self.keywords = tuple(map(str.casefold, keywords) if ignorecase else keywords)
        self.ignorecase = ignorecase


    def __repr__(self) -> str:
        return f"Keywords(keywords={self.keywords})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, KeywordsRule) and frozenset(
            self.keywords
        ) == frozenset(other.keywords)

    def __hash__(self) -> int:
        return hash(frozenset(self.keywords))

    async def __call__(self, event: Event, rule_state: _RuleStateT) -> bool:
        try:
            text = event.get_plain_text()
        except Exception:
            return False
        if not text:
            return False
        text = text.casefold() if self.ignorecase else text
        if keys := tuple(k for k in self.keywords if k in text):
            rule_state[KEYWORD_KEY] = keys
            return True
        return False


class RegexRule:
    """检查消息字符串是否符合指定正则表达式。

    Args:
        regex: 正则表达式
        flags: 正则表达式标记
    """

    __slots__ = ("flags", "regex")

    def __init__(self, regex: str, flags: int = 0):
        self.regex = regex
        self.flags = flags

    def __repr__(self) -> str:
        return f"Regex(regex={self.regex!r}, flags={self.flags})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, RegexRule)
            and self.regex == other.regex
            and self.flags == other.flags
        )

    def __hash__(self) -> int:
        return hash((self.regex, self.flags))

    async def __call__(self, event: Event, rule_state: _RuleStateT) -> bool:
        try:
            msg = event.get_message()
        except Exception:
            return False
        if matched := re.search(self.regex, str(msg), self.flags):
            rule_state[REGEX_MATCHED] = matched
            return True
        else:
            return False


class Counter:
    """计数器，用于跟踪 True/False 事件的发生时间。"""

    __slots__ = ("values")

    def __init__(self, max_size: int):
        self.values = deque(maxlen=max_size)

    def append(self, value: bool, time: Optional[Union[int, float]] = None):
        """记录一个布尔值及其发生时间。"""
        self.values.append((value, time if time is not None else time_util.time()))

    def count_time(self, time_window: Union[int, float], time: Optional[Union[int, float]] = None) -> int:
        """返回 `time_window` 秒内 `True` 发生的次数。"""
        if time is None:
            time = time_util.time()
        return sum(1 for v, t in self.values if t >= time - time_window and t < time and v)

    def count_events(self, count_window: int) -> int:
        """返回最近 `count_window` 条记录中 `True` 发生的次数。"""
        return sum(1 for v, _ in list(self.values)[-count_window:] if v)

class CountTriggerRule:

    __slots__ = ("name", "func", "min_trigger", "time_window", "count_window", "max_size")

    def __init__(
        self,
        name: str,
        func: Dependency[bool] | None = None,  
        min_trigger: int = 10,
        time_window: int = 60,
        count_window: int = 30,
        max_size: int | None = 100
    ):
        self.func = func
        self.name = name
        self.min_trigger = min_trigger
        self.time_window = time_window
        self.count_window = count_window
        self.max_size = max_size

    def __repr__(self) -> str:
        return f"Counter(session_id={self.name}, time_window={self.time_window}, count_window={self.count_window})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, CountTriggerRule)
            and self.name == other.name
            and self.time_window == other.time_window
            and self.count_window == other.count_window
        )

    def __hash__(self) -> int:
        return hash((self.name, self.time_window, self.count_window))

    async def __call__(
        self, 
        bot: "Bot",
        event: Event, 
        rule_state: _RuleStateT,
        bot_state: _BotStateT
    ) -> bool:

        counter: Counter = bot_state[COUNTER_STATE].setdefault(self.name, Counter(self.max_size))
        if self.func:
            counter.append(await solve_dependencies_in_bot(
                self.func,
                bot=bot,
                event=event,
                rule_state=rule_state,
                bot_state=bot_state,
            ))
        else:
            counter.append(True)

        trigger_state = {}
        if self.time_window and (time_trigger := counter.count_time(self.time_window)) >= self.min_trigger:
            trigger_state[f"time_trigger_{self.time_window}s"] = time_trigger
        if self.count_window and (count_trigger := counter.count_events(self.count_window)) >= self.min_trigger:
            trigger_state[f"count_trigger_{self.count_window}"] = count_trigger

        if trigger_state:
            rule_state[COUNTER_INFO] = trigger_state
            return True

        return False


class TrieRule:
    prefix: CharTrie = CharTrie()

    @classmethod
    def add_prefix(cls: Self, prefix: str, value: TRIE_VALUE) -> None:
        if prefix in cls.prefix:
            logger.warning(f'Duplicated prefix rule "{prefix}"')
            return
        cls.prefix[prefix] = value

    @classmethod
    def get_value(cls, bot: "Bot", event: Event, rule_state: _RuleStateT) -> CMD_RESULT:
        prefix = CMD_RESULT(
            command=None,
            raw_command=None,
            command_arg=None,
            command_start=None,
            command_whitespace=None,
        )
        rule_state[PREFIX_KEY] = prefix
        if event.type != "message":
            return prefix

        message = event.get_message()
        message_seg: MessageSegment = message[0]
        if message_seg.is_text():
            segment_text = str(message_seg).lstrip()
            if pf := cls.prefix.longest_prefix(segment_text):
                value: TRIE_VALUE = pf.value
                prefix[RAW_CMD_KEY] = pf.key
                prefix[CMD_START_KEY] = value.command_start
                prefix[CMD_KEY] = value.command

                msg = message.copy()
                msg.pop(0)

                # check whitespace
                arg_str = segment_text[len(pf.key) :]
                arg_str_stripped = arg_str.lstrip()
                # check next segment until arg detected or no text remain
                while not arg_str_stripped and msg and msg[0].is_text():
                    arg_str += str(msg.pop(0))
                    arg_str_stripped = arg_str.lstrip()

                has_arg = arg_str_stripped or msg
                if (
                    has_arg
                    and (stripped_len := len(arg_str) - len(arg_str_stripped)) > 0
                ):
                    prefix[CMD_WHITESPACE_KEY] = arg_str[:stripped_len]

                # construct command arg
                if arg_str_stripped:
                    new_message = msg.__class__(arg_str_stripped)
                    for new_segment in reversed(new_message):
                        msg.insert(0, new_segment)
                prefix[CMD_ARG_KEY] = msg

        return prefix


'''
class CommandRule:
    """检查消息是否为指定命令。

    Args:
        cmds: 指定命令元组列表
        force_whitespace: 是否强制命令后必须有指定空白符
    """

    __slots__ = ("cmds", "force_whitespace")

    def __init__(
        self,
        cmds: list[tuple[str, ...]],
        force_whitespace: Optional[Union[str, bool]] = None,
    ):
        self.cmds = tuple(cmds)
        self.force_whitespace = force_whitespace

    def __repr__(self) -> str:
        return f"Command(cmds={self.cmds})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CommandRule) and frozenset(self.cmds) == frozenset(
            other.cmds
        )

    def __hash__(self) -> int:
        return hash((frozenset(self.cmds),))

    async def __call__(
        self,
        cmd: Optional[tuple[str, ...]] = Command(),
        cmd_arg: Optional[Message] = CommandArg(),
        cmd_whitespace: str | None = CommandWhitespace(),
    ) -> bool:
        if cmd not in self.cmds:
            return False
        if self.force_whitespace is None or not cmd_arg:
            return True
        if isinstance(self.force_whitespace, str):
            return self.force_whitespace == cmd_whitespace
        return self.force_whitespace == (cmd_whitespace is not None)


def command(
    *cmds: Union[str, tuple[str, ...]],
    force_whitespace: Optional[Union[str, bool]] = None,
) -> Rule:
    """匹配消息命令。

    根据配置里提供的 {ref}``command_start` <nonebot.config.Config.command_start>`,
    {ref}``command_sep` <nonebot.config.Config.command_sep>` 判断消息是否为命令。

    可以通过 {ref}`nonebot.params.Command` 获取匹配成功的命令（例: `("test",)`），
    通过 {ref}`nonebot.params.RawCommand` 获取匹配成功的原始命令文本（例: `"/test"`），
    通过 {ref}`nonebot.params.CommandArg` 获取匹配成功的命令参数。

    Args:
        cmds: 命令文本或命令元组
        force_whitespace: 是否强制命令后必须有指定空白符

    用法:
        使用默认 `command_start`, `command_sep` 配置情况下：

        命令 `("test",)` 可以匹配: `/test` 开头的消息
        命令 `("test", "sub")` 可以匹配: `/test.sub` 开头的消息

    :::tip 提示
    命令内容与后续消息间无需空格!
    :::
    """

    config = get_driver().config
    command_start = config.command_start
    command_sep = config.command_sep
    commands: list[tuple[str, ...]] = []
    for command in cmds:
        if isinstance(command, str):
            command = (command,)

        commands.append(command)

        if len(command) == 1:
            for start in command_start:
                TrieRule.add_prefix(f"{start}{command[0]}", TRIE_VALUE(start, command))
        else:
            for start, sep in product(command_start, command_sep):
                TrieRule.add_prefix(
                    f"{start}{sep.join(command)}", TRIE_VALUE(start, command)
                )

    return Rule(CommandRule(commands, force_whitespace))


class ArgumentParser(ArgParser):
    """`shell_like` 命令参数解析器，解析出错时不会退出程序。

    支持 {ref}`nonebot.adapters.Message` 富文本解析。

    用法:
        用法与 `argparse.ArgumentParser` 相同，
        参考文档: [argparse](https://docs.python.org/3/library/argparse.html)
    """

    if TYPE_CHECKING:

        @overload
        def parse_known_args(
            self,
            args: Optional[Sequence[Union[str, MessageSegment]]] = None,
            namespace: None = None,
        ) -> tuple[Namespace, list[Union[str, MessageSegment]]]: ...

        @overload
        def parse_known_args(
            self, args: Optional[Sequence[Union[str, MessageSegment]]], namespace: T
        ) -> tuple[T, list[Union[str, MessageSegment]]]: ...

        @overload
        def parse_known_args(
            self, *, namespace: T
        ) -> tuple[T, list[Union[str, MessageSegment]]]: ...

        def parse_known_args(  # pyright: ignore[reportIncompatibleMethodOverride]
            self,
            args: Optional[Sequence[Union[str, MessageSegment]]] = None,
            namespace: Optional[T] = None,
        ) -> tuple[Union[Namespace, T], list[Union[str, MessageSegment]]]: ...

    @overload
    def parse_args(
        self,
        args: Optional[Sequence[Union[str, MessageSegment]]] = None,
        namespace: None = None,
    ) -> Namespace: ...

    @overload
    def parse_args(
        self, args: Optional[Sequence[Union[str, MessageSegment]]], namespace: T
    ) -> T: ...

    @overload
    def parse_args(self, *, namespace: T) -> T: ...

    def parse_args(
        self,
        args: Optional[Sequence[Union[str, MessageSegment]]] = None,
        namespace: Optional[T] = None,
    ) -> Union[Namespace, T]:
        result, argv = self.parse_known_args(args, namespace)
        if argv:
            msg = gettext("unrecognized arguments: %s")
            self.error(msg % " ".join(map(str, argv)))
        return cast(Union[Namespace, T], result)

    def _parse_optional(
        self, arg_string: Union[str, MessageSegment]
    ) -> Optional[tuple[Optional[Action], str, str | None]]:
        return (
            super()._parse_optional(arg_string) if isinstance(arg_string, str) else None
        )

    def _print_message(self, message: str, file: Optional[IO[str]] = None):  # type: ignore
        if (msg := parser_message.get(None)) is not None:
            parser_message.set(msg + message)
        else:
            super()._print_message(message, file)

    def exit(self, status: int = 0, message: str | None = None):
        if message:
            self._print_message(message)
        raise ParserExit(status=status, message=parser_message.get(None))


class ShellCommandRule:
    """检查消息是否为指定 shell 命令。

    Args:
        cmds: 指定命令元组列表
        parser: 可选参数解析器
    """

    __slots__ = ("cmds", "parser")

    def __init__(self, cmds: list[tuple[str, ...]], parser: Optional[ArgumentParser]):
        self.cmds = tuple(cmds)
        self.parser = parser

    def __repr__(self) -> str:
        return f"ShellCommand(cmds={self.cmds}, parser={self.parser})"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, ShellCommandRule)
            and frozenset(self.cmds) == frozenset(other.cmds)
            and self.parser is other.parser
        )

    def __hash__(self) -> int:
        return hash((frozenset(self.cmds), self.parser))

    async def __call__(
        self,
        rule_state: _RuleStateT,
        cmd: Optional[tuple[str, ...]] = Command(),
        msg: Optional[Message] = CommandArg(),
    ) -> bool:
        if cmd not in self.cmds or msg is None:
            return False

        try:
            rule_state[SHELL_ARGV] = list(
                chain.from_iterable(
                    shlex.split(str(seg))
                    if cast(MessageSegment, seg).is_text()
                    else (seg,)
                    for seg in msg
                )
            )
        except Exception as e:
            # set SHELL_ARGV to none indicating shlex error
            rule_state[SHELL_ARGV] = None
            # ensure SHELL_ARGS is set to ParserExit if parser is provided
            if self.parser:
                rule_state[SHELL_ARGS] = ParserExit(status=2, message=str(e))
            return True

        if self.parser:
            t = parser_message.set("")
            try:
                args = self.parser.parse_args(rule_state[SHELL_ARGV])
                rule_state[SHELL_ARGS] = args
            except ArgumentError as e:
                rule_state[SHELL_ARGS] = ParserExit(status=2, message=str(e))
            except ParserExit as e:
                rule_state[SHELL_ARGS] = e
            finally:
                parser_message.reset(t)
        return True


def shell_command(
    *cmds: Union[str, tuple[str, ...]], parser: Optional[ArgumentParser] = None
) -> Rule:
    """匹配 `shell_like` 形式的消息命令。

    根据配置里提供的 {ref}``command_start` <nonebot.config.Config.command_start>`,
    {ref}``command_sep` <nonebot.config.Config.command_sep>` 判断消息是否为命令。

    可以通过 {ref}`nonebot.params.Command` 获取匹配成功的命令
    （例: `("test",)`），
    通过 {ref}`nonebot.params.RawCommand` 获取匹配成功的原始命令文本
    （例: `"/test"`），
    通过 {ref}`nonebot.params.ShellCommandArgv` 获取解析前的参数列表
    （例: `["arg", "-h"]`），
    通过 {ref}`nonebot.params.ShellCommandArgs` 获取解析后的参数字典
    （例: `{"arg": "arg", "h": True}`）。

    :::caution 警告
    如果参数解析失败，则通过 {ref}`nonebot.params.ShellCommandArgs`
    获取的将是 {ref}`nonebot.exception.ParserExit` 异常。
    :::

    Args:
        cmds: 命令文本或命令元组
        parser: {ref}`nonebot.rule.ArgumentParser` 对象

    用法:
        使用默认 `command_start`, `command_sep` 配置，更多示例参考
        [argparse](https://docs.python.org/3/library/argparse.html) 标准库文档。

        ```python
        from nonebot.rule import ArgumentParser

        parser = ArgumentParser()
        parser.add_argument("-a", action="store_true")

        rule = shell_command("ls", parser=parser)
        ```

    :::tip 提示
    命令内容与后续消息间无需空格!
    :::
    """
    if parser is not None and not isinstance(parser, ArgumentParser):
        raise TypeError("`parser` must be an instance of nonebot.rule.ArgumentParser")

    config = get_driver().config
    command_start = config.command_start
    command_sep = config.command_sep
    commands: list[tuple[str, ...]] = []
    for command in cmds:
        if isinstance(command, str):
            command = (command,)

        commands.append(command)

        if len(command) == 1:
            for start in command_start:
                TrieRule.add_prefix(f"{start}{command[0]}", TRIE_VALUE(start, command))
        else:
            for start, sep in product(command_start, command_sep):
                TrieRule.add_prefix(
                    f"{start}{sep.join(command)}", TRIE_VALUE(start, command)
                )

    return Rule(ShellCommandRule(commands, parser))
'''
class ToMeRule:
    """检查事件是否与机器人有关。"""

    __slots__ = ()

    def __repr__(self) -> str:
        return "ToMe()"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ToMeRule)

    def __hash__(self) -> int:
        return hash((self.__class__,))

    async def __call__(self, event: Event) -> bool:
        return event.is_tome()


__autodoc__ = {
    "Rule": True,
    "Rule.__call__": True,
    "TrieRule": False,
    "ArgumentParser.exit": False,
    "ArgumentParser.parse_args": False,
}