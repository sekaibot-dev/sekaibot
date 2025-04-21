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

import re
import shlex
from argparse import Action, ArgumentError, Namespace
from argparse import ArgumentParser as ArgParser
from collections.abc import Hashable, Sequence
from contextvars import ContextVar
from gettext import gettext
from itertools import chain, product
from pathlib import Path
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    NamedTuple,
    Never,
    TypedDict,
    TypeVar,
    cast,
    overload,
)
from typing_extensions import override

from pygtrie import CharTrie  # type: ignore

from sekaibot.consts import (
    BOT_GLOBAL_KEY,
    CMD_ARG_KEY,
    CMD_KEY,
    CMD_START_KEY,
    CMD_WHITESPACE_KEY,
    COUNTER_LATEST_TIGGERS,
    COUNTER_STATE,
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
from sekaibot.exceptions import ParserExit
from sekaibot.internal.event import Event
from sekaibot.internal.message import Message, MessageSegment
from sekaibot.internal.rule import Rule
from sekaibot.log import logger
from sekaibot.typing import GlobalStateT, NameT, StateT

from ._counter import Counter

if TYPE_CHECKING:
    from sekaibot.bot import Bot

T = TypeVar("T")


class CommandResult(TypedDict):
    """命令匹配结果类"""

    command: tuple[str, ...] | None
    raw_command: str | None
    command_arg: Message[Any] | None
    command_start: str | None
    command_whitespace: str | None


class TrieValue(NamedTuple):
    """Trie参数"""

    command_start: str
    command: tuple[str, ...]


parser_message: ContextVar[str] = ContextVar("parser_message")


class StartswithRule:
    """检查消息富文本是否以指定字符串或 MessageSegment 开头。

    Args:
        msgs: 指定消息开头字符串或 MessageSegment 元组
        ignorecase: 是否忽略大小写
    """

    __slots__ = ("ignorecase", "msgs")

    def __init__(
        self, msgs: tuple[str | MessageSegment[Any], ...], ignorecase: bool = False
    ) -> None:
        self.msgs = msgs
        self.ignorecase = ignorecase

    @override
    def __repr__(self) -> str:
        return f"Startswith(msg={self.msgs}, ignorecase={self.ignorecase})"

    @override
    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, StartswithRule)
            and frozenset(self.msgs) == frozenset(other.msgs)
            and self.ignorecase == other.ignorecase
        )

    @override
    def __hash__(self) -> int:
        return hash((frozenset(self.msgs), self.ignorecase))

    async def __call__(self, event: Event[Any], state: StateT) -> bool:
        """检查消息富文本是否以指定字符串或 MessageSegment 开头。"""
        try:
            message = event.get_message()
        except Exception:
            return False
        if match := message.startswith(
            self.msgs, ignorecase=self.ignorecase, return_key=True
        ):
            state[STARTSWITH_KEY] = match
            return True
        return False


class EndswithRule:
    """检查消息富文本是否以指定字符串或 MessageSegment 结尾。

    Args:
        msgs: 指定消息开头字符串或 MessageSegment 元组
        ignorecase: 是否忽略大小写
    """

    __slots__ = ("ignorecase", "msgs")

    def __init__(
        self, msgs: tuple[str | MessageSegment[Any], ...], ignorecase: bool = False
    ) -> None:
        self.msgs = msgs
        self.ignorecase = ignorecase

    @override
    def __repr__(self) -> str:
        return f"Endswith(msg={self.msgs}, ignorecase={self.ignorecase})"

    @override
    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, EndswithRule)
            and frozenset(self.msgs) == frozenset(other.msgs)
            and self.ignorecase == other.ignorecase
        )

    @override
    def __hash__(self) -> int:
        return hash((frozenset(self.msgs), self.ignorecase))

    async def __call__(self, event: Event[Any], state: StateT) -> bool:
        """检查消息富文本是否以指定字符串或 MessageSegment 结尾。"""
        try:
            message = event.get_message()
        except Exception:
            return False
        if match := message.endswith(
            self.msgs, ignorecase=self.ignorecase, return_key=True
        ):
            state[ENDSWITH_KEY] = match
            return True
        return False


class FullmatchRule:
    """检查消息纯文本是否与指定字符串全匹配。

    Args:
        msgs: 指定消息全匹配字符串集合
        ignorecase: 是否忽略大小写
    """

    __slots__ = ("ignorecase", "msgs")

    def __init__(
        self,
        msgs: tuple[str | Message[Any] | MessageSegment[Any], ...],
        ignorecase: bool = False,
    ) -> None:
        self.msgs = cast(
            "set[str | Message[Any]]",
            {
                msg.casefold()
                if ignorecase and isinstance(msg, str)
                else msg.get_message_class()(msg)
                if isinstance(msg, MessageSegment)
                else cast("Hashable", msg)
                for msg in msgs
            },
        )
        self.ignorecase = ignorecase

    @override
    def __repr__(self) -> str:
        return f"Fullmatch(msg={self.msgs}, ignorecase={self.ignorecase})"

    @override
    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, FullmatchRule)
            and frozenset(self.msgs) == frozenset(other.msgs)
            and self.ignorecase == other.ignorecase
        )

    @override
    def __hash__(self) -> int:
        return hash((frozenset(self.msgs), self.ignorecase))

    async def __call__(self, event: Event[Any], state: StateT) -> bool:
        """检查消息纯文本是否与指定字符串全匹配。"""
        try:
            text = event.get_plain_text()
            message = event.get_message()
        except Exception:
            return False
        if not text:
            return False
        text = text.casefold() if self.ignorecase else text

        if text in self.msgs:
            state[FULLMATCH_KEY] = text
            return True
        if message in self.msgs:
            state[FULLMATCH_KEY] = message
            return True
        return False


class KeywordsRule:
    """检查消息纯文本是否包含指定关键字。

    Args:
        keywords: 指定关键字集合
    """

    __slots__ = ("ignorecase", "keywords")

    def __init__(
        self, keywords: tuple[str | MessageSegment[Any], ...], ignorecase: bool = False
    ) -> None:
        self.keywords = {
            keyword.casefold() if ignorecase and isinstance(keyword, str) else keyword
            for keyword in keywords
        }
        self.ignorecase = ignorecase

    @override
    def __repr__(self) -> str:
        return f"Keywords(keywords={self.keywords}, ignorecase={self.ignorecase})"

    @override
    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, KeywordsRule)
            and frozenset(self.keywords) == frozenset(other.keywords)
            and self.ignorecase == other.ignorecase
        )

    @override
    def __hash__(self) -> int:
        return hash(frozenset(self.keywords))

    async def __call__(self, event: Event[Any], state: StateT) -> bool:
        """检查消息纯文本是否包含指定关键字。"""
        try:
            text = event.get_plain_text()
            message = event.get_message()
        except Exception:
            return False
        if not text:
            return False
        text = text.casefold() if self.ignorecase else text
        if keys := tuple(
            k
            for k in self.keywords
            if (isinstance(k, str) and (k in text)) or k in message
        ):
            state[KEYWORD_KEY] = keys
            return True
        return False


class WordFilterRule:
    """检查消息纯文本是否包含指定关键字，用于敏感词过滤。

    Args:
        words: 指定关键字集合
        word_file: 可选的词库文件路径 (每行一个词)
        ignorecase: 是否忽略大小写
        use_pinyin: 是否启用拼音匹配，使用 `pypinyin` 库
        use_aho: 是否启用 Aho-Corasick 算法 (当词数较大时自动激活) ，使用 `pyahocorasick` 库
    """

    __slots__ = ("_automaton", "ignorecase", "use_aho", "use_pinyin", "words")

    def __init__(
        self,
        words: tuple[str, ...] = (),
        word_file: Path | None = None,
        ignorecase: bool = False,
        use_pinyin: bool = False,
        use_aho: bool = False,
    ) -> None:
        self.ignorecase = ignorecase
        self.words: set[str] = set()
        self.use_aho = use_aho
        self._automaton = None

        if word_file:
            self._load_word_set(word_file)

        self.words.update(
            word.casefold() if ignorecase and isinstance(word, str) else word
            for word in words
        )

        self.use_pinyin = use_pinyin

        if self.use_pinyin:
            try:
                from pypinyin import Style, lazy_pinyin
            except ImportError:
                raise ImportError(
                    "pypinyin is not installed, please install it first."
                ) from None

            self.words = {
                "".join(lazy_pinyin(word, style=Style.FIRST_LETTER)).casefold()
                if ignorecase
                else "".join(lazy_pinyin(word, style=Style.FIRST_LETTER))
                for word in self.words
            }

        min_aho_words = 2000
        if self.use_aho and len(self.words) > min_aho_words:
            try:
                from ahocorasick import Automaton  # type: ignore

                self._automaton = cast("Any", Automaton())
                for idx, word in enumerate(self.words):
                    self._automaton.add_word(word, (idx, word))
                self._automaton.make_automaton()
            except ImportError:
                raise ImportError(
                    "pyahocorasick is not installed, please install it first."
                ) from None

    @override
    def __repr__(self) -> str:
        return (
            f"WordFilter(words={self.words}, ignorecase={self.ignorecase}, "
            f"pinyin={self.use_pinyin}, use_aho={self.use_aho})"
        )

    @override
    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, WordFilterRule)
            and frozenset(self.words) == frozenset(other.words)
            and self.ignorecase == other.ignorecase
            and self.use_pinyin == other.use_pinyin
            and self.use_aho == other.use_aho
        )

    @override
    def __hash__(self) -> int:
        return hash(
            (frozenset(self.words), self.ignorecase, self.use_pinyin, self.use_aho)
        )

    async def __call__(self, event: Event[Any]) -> bool:
        """执行敏感词检测。

        Return:
            bool: 如果消息合法 (不包含敏感词) 返回 True，否则 False
        """
        try:
            text = event.get_plain_text()
        except Exception:
            return True
        if not text:
            return True

        text = text.casefold() if self.ignorecase else text

        if self.use_pinyin:
            try:
                from pypinyin import Style, lazy_pinyin
            except ImportError:
                raise ImportError(
                    "pypinyin is not installed, please install it first."
                ) from None

            text += "".join(lazy_pinyin(text, style=Style.FIRST_LETTER))

        if self._automaton:  # type: ignore
            return not any(True for _, (_, word) in self._automaton.iter(text))  # type: ignore

        return not any(word in text for word in self.words)

    def _load_word_set(self, file_path: Path) -> None:
        """从 txt 文件加载敏感词，每行一个词。

        Args:
            file_path (Path): txt 文件 Path
        """
        if not file_path.is_file():
            raise FileNotFoundError(f"File {file_path} not found.")

        word_set: list[str] = []
        try:
            with file_path.open(encoding="utf-8") as file:
                for _, line in enumerate(file, start=1):
                    word = line.strip()
                    if word:
                        word_set.append(word)
        except (OSError, UnicodeDecodeError) as e:
            raise RuntimeError("Read file error") from e

        self.words.update(
            word.casefold() if self.ignorecase and isinstance(word, str) else word
            for word in word_set
        )


class RegexRule:
    """检查消息字符串是否符合指定正则表达式。

    Args:
        regex: 正则表达式
        flags: 正则表达式标记
    """

    __slots__ = ("flags", "regex")

    def __init__(self, regex: str, flags: int = 0) -> None:
        self.regex = regex
        self.flags = flags

    @override
    def __repr__(self) -> str:
        return f"Regex(regex={self.regex!r}, flags={self.flags})"

    @override
    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, RegexRule)
            and self.regex == other.regex
            and self.flags == other.flags
        )

    @override
    def __hash__(self) -> int:
        return hash((self.regex, self.flags))

    async def __call__(self, event: Event[Any], state: StateT) -> bool:
        """检查消息字符串是否符合指定正则表达式。"""
        try:
            msg = event.get_message()
        except Exception:
            return False
        if matched := re.search(self.regex, str(msg), self.flags):
            state[REGEX_MATCHED] = matched
            return True
        return False


class CountTriggerRule:
    """计数器规则。"""

    __slots__ = ("count_window", "max_size", "min_trigger", "rule", "time_window")

    def __init__(
        self,
        time_window: int = 60,
        count_window: int = 30,
        min_trigger: int = 10,
        max_size: int | None = 100,
        rule: Rule | None = None,
    ) -> None:
        self.rule = rule
        self.min_trigger = min_trigger
        self.time_window = time_window
        self.count_window = count_window
        self.max_size = max_size

    @override
    def __repr__(self) -> str:
        return (
            f"Counter(time_window={self.time_window}, count_window={self.count_window}, "
            f"min_trigger={self.min_trigger}, max_size={self.max_size}, rule={self.rule!r})"
        )

    @override
    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, CountTriggerRule)
            and self.time_window == other.time_window
            and self.count_window == other.count_window
            and self.min_trigger == other.min_trigger
            and self.max_size == other.max_size
            and self.rule == other.rule
        )

    @override
    def __hash__(self) -> int:
        return hash(
            (self.time_window, self.count_window, self.min_trigger, self.max_size)
        )

    async def __call__(
        self,
        name: NameT,
        bot: "Bot",
        event: Event[Any],
        state: StateT,
        global_state: GlobalStateT,
    ) -> bool:
        """计数器规则。"""
        if isinstance(global_state[BOT_GLOBAL_KEY][COUNTER_STATE], dict):
            counter: Counter[Event[Any]] = global_state[BOT_GLOBAL_KEY][
                COUNTER_STATE
            ].setdefault(name, Counter[Event[Any]](self.max_size))
        else:
            counter = Counter[Event[Any]](self.max_size)
            global_state[BOT_GLOBAL_KEY][COUNTER_STATE] = {name: counter}

        if self.rule:
            counter.record(
                event,
                await self.rule(
                    bot=bot,
                    event=event,
                    state=state,
                    global_state=global_state,
                ),
                getattr(event, "time", None),
            )
        else:
            counter.record(event, True, getattr(event, "time", None))

        trigger = False
        if (
            self.time_window
            and len(
                time_trigger := tuple(
                    counter.iter_in_time(self.time_window, getattr(event, "time", None))
                )
            )
            >= self.min_trigger
        ):
            state[COUNTER_TIME_TIGGERS] = time_trigger
            trigger = True
        if (
            self.count_window
            and len(count_trigger := tuple(counter.iter_in_latest(self.count_window)))
            >= self.min_trigger
        ):
            state[COUNTER_LATEST_TIGGERS] = count_trigger
            trigger = True
        return trigger


class TrieRule:
    """Trie 规则类"""

    prefix: Any

    def __init__(self) -> None:
        self.prefix: Any = cast("Any", CharTrie())

    def add_prefix(self, prefix: str, value: TrieValue) -> None:
        """添加 prefix"""
        if prefix in self.prefix:
            logger.warning(f'Duplicated prefix rule "{prefix}"')
            return
        self.prefix[prefix] = value

    def get_value(self, event: Event[Any], state: StateT) -> CommandResult:
        """获取解析结果"""
        prefix = CommandResult(
            command=None,
            raw_command=None,
            command_arg=None,
            command_start=None,
            command_whitespace=None,
        )
        state[PREFIX_KEY] = prefix
        if event.type != "message":
            return prefix

        message = event.get_message()
        message_seg: MessageSegment[Any] = message[0]
        if message_seg.is_text():
            segment_text = str(message_seg).lstrip()
            if pf := self.prefix.longest_prefix(segment_text):
                value: TrieValue = pf.value
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


class CommandRule:
    """检查消息是否为指定命令。

    Args:
        cmds: 指定命令元组列表
        force_whitespace: 是否强制命令后必须有指定空白符
    """

    __slots__ = ("char_trie", "cmds", "force_whitespace")

    def __init__(
        self,
        cmds: tuple[tuple[str, ...], ...],
        force_whitespace: str | bool | None = None,
    ) -> None:
        self.cmds = cmds
        self.force_whitespace = force_whitespace
        self.char_trie = TrieRule()

        from sekaibot.bot import Bot

        Bot.bot_startup_hook(self._set_prefix)

    def _set_prefix(self, bot: "Bot") -> None:
        command_start = bot.config.rule.command_start
        command_sep = bot.config.rule.command_sep

        commands: list[tuple[str, ...]] = []
        for command in self.cmds:
            if isinstance(command, str):
                command = (command,)

            commands.append(command)

            if len(command) == 1:
                for start in command_start:
                    self.char_trie.add_prefix(
                        f"{start}{command[0]}", TrieValue(start, command)
                    )
            else:
                for start, sep in product(command_start, command_sep):
                    self.char_trie.add_prefix(
                        f"{start}{sep.join(command)}", TrieValue(start, command)
                    )

    @override
    def __repr__(self) -> str:
        return f"Command(cmds={self.cmds})"

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, CommandRule) and frozenset(self.cmds) == frozenset(
            other.cmds
        )

    @override
    def __hash__(self) -> int:
        return hash((frozenset(self.cmds),))

    async def __call__(
        self,
        event: Event[Any],
        state: StateT,
    ) -> bool:
        """检查消息是否为指定命令。"""
        self.char_trie.get_value(event, state)

        cmd = state[PREFIX_KEY][CMD_KEY]
        cmd_arg = state[PREFIX_KEY][CMD_ARG_KEY]
        cmd_whitespace = state[PREFIX_KEY][CMD_WHITESPACE_KEY]

        if cmd not in self.cmds:
            return False
        if self.force_whitespace is None or not cmd_arg:
            return True
        if isinstance(self.force_whitespace, str):
            return self.force_whitespace == cmd_whitespace
        return self.force_whitespace == (cmd_whitespace is not None)


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
            args: Sequence[str | MessageSegment[Any]] | None = None,
            namespace: None = None,
        ) -> tuple[Namespace, list[str | MessageSegment[Any]]]: ...

        @overload
        def parse_known_args(
            self, args: Sequence[str | MessageSegment[Any]] | None, namespace: T
        ) -> tuple[T, list[str | MessageSegment[Any]]]: ...

        @overload
        def parse_known_args(
            self, *, namespace: T
        ) -> tuple[T, list[str | MessageSegment[Any]]]: ...

        def parse_known_args(  # type: ignore  # noqa: D102
            self,
            args: Sequence[str | MessageSegment[Any]] | None = None,
            namespace: T | None = None,
        ) -> tuple[Namespace | T, list[str | MessageSegment[Any]]]: ...

    @overload
    def parse_args(
        self,
        args: Sequence[str | MessageSegment[Any]] | None = None,
        namespace: None = None,
    ) -> Namespace: ...

    @overload
    def parse_args(
        self, args: Sequence[str | MessageSegment[Any]] | None, namespace: T
    ) -> T: ...

    @overload
    def parse_args(self, *, namespace: T) -> T: ...

    @override
    def parse_args(
        self,
        args: Sequence[str | MessageSegment[Any]] | None = None,
        namespace: T | None = None,
    ) -> Namespace | T:
        result, argv = self.parse_known_args(args, namespace)
        if argv:
            msg = gettext("unrecognized arguments: %s")
            self.error(msg % " ".join(map(str, argv)))
        return cast("Namespace | T", result)

    @override
    def _parse_optional(
        self, arg_string: str | MessageSegment[Any]
    ) -> tuple[Action | None, str, str | None] | None:
        return (
            super()._parse_optional(arg_string) if isinstance(arg_string, str) else None
        )

    def _print_message(self, message: str, file: IO[str] | None = None) -> None:  # type: ignore
        if (msg := parser_message.get(None)) is not None:
            parser_message.set(msg + message)
        else:
            super()._print_message(message, file)

    @override
    def exit(self, status: int = 0, message: str | None = None) -> Never:
        if message:
            self._print_message(message)
        raise ParserExit(status=status, message=parser_message.get(None))


class ShellCommandRule:
    """检查消息是否为指定 shell 命令。

    Args:
        cmds: 指定命令元组列表
        parser: 可选参数解析器
    """

    __slots__ = ("char_trie", "cmds", "parser")

    def __init__(
        self, cmds: tuple[tuple[str, ...], ...], parser: ArgumentParser | None
    ) -> None:
        if parser is not None and not isinstance(parser, ArgumentParser):
            raise TypeError(
                "`parser` must be an instance of nonebot.rule.ArgumentParser"
            )

        self.cmds = cmds
        self.parser = parser
        self.char_trie = TrieRule()

        from sekaibot.bot import Bot

        Bot.bot_startup_hook(self._set_prefix)

    def _set_prefix(self, bot: "Bot") -> None:
        command_start = bot.config.rule.command_start
        command_sep = bot.config.rule.command_sep
        commands: list[tuple[str, ...]] = []
        for command in self.cmds:
            if isinstance(command, str):
                command = (command,)

            commands.append(command)

            if len(command) == 1:
                for start in command_start:
                    self.char_trie.add_prefix(
                        f"{start}{command[0]}", TrieValue(start, command)
                    )
            else:
                for start, sep in product(command_start, command_sep):
                    self.char_trie.add_prefix(
                        f"{start}{sep.join(command)}", TrieValue(start, command)
                    )

    @override
    def __repr__(self) -> str:
        return f"ShellCommand(cmds={self.cmds}, parser={self.parser})"

    @override
    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, ShellCommandRule)
            and frozenset(self.cmds) == frozenset(other.cmds)
            and self.parser is other.parser
        )

    @override
    def __hash__(self) -> int:
        return hash((frozenset(self.cmds), self.parser))

    async def __call__(
        self,
        event: Event[Any],
        state: StateT,
    ) -> bool:
        """检查消息是否为指定 shell 命令。"""
        self.char_trie.get_value(event, state)

        cmd = state[PREFIX_KEY][CMD_KEY]
        msg = state[PREFIX_KEY][CMD_ARG_KEY]

        if cmd not in self.cmds or msg is None:
            return False

        try:
            state[SHELL_ARGV] = list(
                chain.from_iterable(
                    shlex.split(str(seg))
                    if cast("MessageSegment[Any]", seg).is_text()
                    else (seg,)
                    for seg in msg
                )
            )
        except Exception as e:
            # set SHELL_ARGV to none indicating shlex error
            state[SHELL_ARGV] = None
            # ensure SHELL_ARGS is set to ParserExit if parser is provided
            if self.parser:
                state[SHELL_ARGS] = ParserExit(status=2, message=str(e))
            return True

        if self.parser:
            t = parser_message.set("")
            try:
                args = self.parser.parse_args(
                    cast(
                        "Sequence[str | MessageSegment[Any]] | None", state[SHELL_ARGV]
                    )
                )
                state[SHELL_ARGS] = args
            except ArgumentError as e:
                state[SHELL_ARGS] = ParserExit(status=2, message=str(e))
            except ParserExit as e:
                state[SHELL_ARGS] = e
            finally:
                parser_message.reset(t)
        return True


class ToMeRule:
    """检查事件是否与机器人有关。"""

    __slots__ = ()

    @override
    def __repr__(self) -> str:
        return "ToMe()"

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, ToMeRule)

    @override
    def __hash__(self) -> int:
        return hash((self.__class__,))

    async def __call__(self, event: Event[Any]) -> bool:
        """检查事件是否与机器人有关。"""
        return event.is_tome()


__autodoc__ = {
    "Rule": True,
    "Rule.__call__": True,
    "TrieRule": False,
    "ArgumentParser.exit": False,
    "ArgumentParser.parse_args": False,
}
