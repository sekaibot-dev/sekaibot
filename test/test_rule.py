import pytest

from sekaibot.consts import ENDSWITH_KEY, STARTSWITH_KEY
from sekaibot.internal.message import Message, MessageSegment
from sekaibot.rule import (
    EndsWith,
    StartsWith,
)


# Fake MessageSegment and Message for testing
class MySeg(MessageSegment["MyMsg"]):
    type: str
    data: dict

    @classmethod
    def get_message_class(cls):
        return MyMsg

    @classmethod
    def from_str(cls, s: str):
        return cls(type="text", data={"text": s})


class MyMsg(Message[MySeg]):
    @classmethod
    def get_segment_class(cls):
        return MySeg


# Fake Event
class FakeEvent:
    def __init__(self, text, segments=None, type_="message", is_tome=True):
        self._text = text
        self._segments = segments or [MySeg(type="text", data={"text": text})]
        self.type = type_
        self._is_tome = is_tome

    def get_message(self):
        return MyMsg(*self._segments)

    def get_plain_text(self):
        return self._text

    def is_tome(self):
        return self._is_tome


@pytest.mark.anyio
async def test_startswith_endswith():
    state = {}
    event = FakeEvent("hello world")
    rule = StartsWith("hello")
    result = await rule._rule(event, state)
    print(event.get_message())
    assert result
    assert rule._param(state) == "hello"

    state = {}
    rule = EndsWith("world")
    result = await rule._rule(event, state)
    assert result
    assert state[ENDSWITH_KEY] == "world"

    state = {}
    rule = StartsWith("bye")
    result = await rule._rule(event, state)
    assert not result
    assert STARTSWITH_KEY not in state

    state = {}
    rule = EndsWith("bye")
    result = await rule._rule(event, state)
    assert not result
    assert ENDSWITH_KEY not in state


"""@pytest.mark.anyio
async def test_fullmatch_keywords():
    state = {}
    event = FakeEvent("foo")
    rule = FullMatch("foo")
    result = await rule.__rule__(event, state)
    assert result
    if result:
        assert state.get("fullmatch") == "foo"

    state = {}
    rule = FullMatch("bar")
    result = await rule.__rule__(event, state)
    assert not result

    state = {}
    event = FakeEvent("this is a keyword test")
    rule = Keywords("keyword")
    result = await rule.__rule__(event, state)
    assert result
    assert "keyword" in state["keyword"]

    # test ignorecase
    state = {}
    rule = Keywords("KEYWORD", ignorecase=True)
    result = await rule.__rule__(event, state)
    assert result


@pytest.mark.anyio
async def test_regex_rule():
    state = {}
    event = FakeEvent("abc123")
    rule = Regex(r"\\d+")
    result = await rule.__rule__(event, state)
    assert result
    if result:
        match = state.get("regex_matched")
        assert isinstance(match, re.Match)
        assert match.group(0) == "123"

    state = {}
    rule = Regex(r"xyz")
    result = await rule.__rule__(event, state)
    assert not result
    assert "regex_matched" not in state


@pytest.mark.anyio
async def test_command_rule():
    # Test single level command
    state = {}
    event = FakeEvent("/test arg1")
    rule = Command(("test",))
    rule.__rule__.char_trie.add_prefix("/test", ("/", ("test",)))
    assert await rule.__rule__(event, state)
    assert state[PREFIX_KEY][CMD_KEY] == ("test",)

    # Test multi-level command with separator
    state = {}
    event = FakeEvent("/test-sub cmd")
    rule = Command(("test", "sub"))
    rule.__rule__.char_trie.add_prefix("/test-sub", ("/", ("test", "sub")))
    assert await rule.__rule__(event, state)

    # Test force_whitespace requirement
    state = {}
    event = FakeEvent("/test123")  # No whitespace after command
    rule = Command(("test",), force_whitespace=True)
    rule.__rule__.char_trie.add_prefix("/test", ("/", ("test",)))
    assert not await rule.__rule__(event, state)


@pytest.mark.anyio
async def test_shell_command_rule():
    from sekaibot.consts import SHELL_ARGS, SHELL_ARGV
    from sekaibot.exceptions import ParserExit

    # Test valid command with arguments
    state = {}
    parser = ArgumentParser()
    parser.add_argument("-a", action="store_true")
    parser.add_argument("--foo")
    from sekaibot.internal.rule.utils import ArgumentParser as SekaiArgumentParser
    parser = SekaiArgumentParser()
    rule = ShellCommand("echo", parser=parser)
    rule.__rule__.char_trie.add_prefix("/echo", ("", ("echo",)))

    # Test normal argument parsing
    valid_event = FakeEvent("/echo -a --foo bar")
    assert await rule.__rule__(valid_event, state)
    assert isinstance(state[SHELL_ARGV], list)
    assert isinstance(state[SHELL_ARGS], Namespace)
    assert state[SHELL_ARGS].a is True
    assert state[SHELL_ARGS].foo == "bar"

    # Test invalid arguments
    state = {}
    invalid_event = FakeEvent("/echo -z")  # Undefined flag
    assert await rule.__rule__(invalid_event, state)
    assert isinstance(state[SHELL_ARGS], ParserExit)
    assert state[SHELL_ARGS].status == 2

    # Test mixed message segments
    state = {}
    mixed_event = FakeEvent(
        "/echo text",
        segments=[
            MySeg(type="text", data={"text": "/echo"}),
            MySeg(type="image", data={"url": "test.jpg"}),
            MySeg(type="text", data={"text": "-a"}),
        ],
    )
    assert await rule.__rule__(mixed_event, state)
    assert state[SHELL_ARGV] == ["-a"]

    # Test empty arguments
    state = {}
    empty_event = FakeEvent("/echo")
    assert await rule.__rule__(empty_event, state)
    assert state[SHELL_ARGV] == []


@pytest.mark.anyio
async def test_wordfilter_rule():
    # Test basic keyword detection
    event_clean = FakeEvent("hello world")
    event_bad = FakeEvent("abc badword xyz")
    rule = WordFilter("badword")
    assert await rule.__rule__(event_clean) is True
    assert await rule.__rule__(event_bad) is False

    # Test case sensitivity
    event_mixed_case = FakeEvent("BadWord")
    rule_case_sensitive = WordFilter("badword", ignorecase=False)
    assert (
        await rule_case_sensitive.__rule__(event_mixed_case) is True
    )  # Should pass since case doesn't match

    # Test file loading with temporary file
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
        f.write("forbidden_term\nb@dw0rd\n敏感词")
        f.flush()

        # Test valid file loading
        rule_file = WordFilter(word_file=f.name)
        event_file_bad = FakeEvent("this has 敏感词")
        assert await rule_file.__rule__(event_file_bad) is False
        event_file_clean = FakeEvent("clean text")
        assert await rule_file.__rule__(event_file_clean) is True

        # Test non-existent file
        with pytest.raises(FileNotFoundError):
            WordFilter(word_file="non_existent_file.txt")

    # Test combined words and file
    with tempfile.NamedTemporaryFile(mode="w+") as f:
        f.write("additional_term")
        f.flush()
        rule_combined = WordFilter("base_term", word_file=f.name)
        assert await rule_combined.__rule__(FakeEvent("base_term")) is False
        assert await rule_combined.__rule__(FakeEvent("additional_term")) is False

    # Test special characters
    rule_special = WordFilter("test$pecial*")
    assert await rule_special.__rule__(FakeEvent("test$pecial*")) is False
    assert await rule_combined.__rule__(FakeEvent("test$pecial")) is True

    # Test pinyin matching
    rule_pinyin = WordFilter("bwd", use_pinyin=True)
    event_pinyin = FakeEvent("百度文档")
    assert await rule_pinyin.__rule__(event_pinyin) is False


@pytest.mark.anyio
async def test_tome_rule():
    # Test message event with tome
    event_message = FakeEvent("msg", type_="message", is_tome=True)
    assert await ToMe().__rule__(event_message)

    # Test non-message event type
    event_notice = FakeEvent("", type_="notice", is_tome=True)
    assert not await ToMe().__rule__(event_notice)

    # Test message event without tome
    event_not_tome = FakeEvent("msg", type_="message", is_tome=False)
    assert not await ToMe().__rule__(event_not_tome)

    # Test mixed message segments
    event_mixed = FakeEvent(
        "msg",
        segments=[
            MySeg(type="mention", data={"user_id": "123"}),
            MySeg(type="text", data={"text": "hello"}),
        ],
    )
    assert await ToMe().__rule__(event_mixed)"""
