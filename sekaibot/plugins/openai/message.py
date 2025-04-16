from __future__ import annotations

import json
from collections.abc import Iterator, MutableSequence
from copy import deepcopy
from typing import Literal, Self, TypeVar

from pydantic import BaseModel, ConfigDict, field_validator

HistoryInput = TypeVar("HistoryInput", str, list["MessageSegment"], "MessageSegment", "History")
Role = Literal["system", "user", "assistant", "tool", "function"]
ContentType = str | list[dict]


class MessageSegment(BaseModel):
    """
    A message item for OpenAI's /v1/chat/completions API.

    Supports system, user, assistant, tool roles and assistant function call instructions.

    Attributes:
        role (Literal): One of 'system', 'user', 'assistant', 'tool'.
        content (str | list[dict]): Message content or multimodal content (for user).
        name (str | None): Required for tool role.
        function_call (dict | None): Only for assistant role when calling a function.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Role
    content: ContentType
    name: str | None = None
    function_call: dict | None = None

    # --- 构造方法 ---
    @classmethod
    def system(cls, content: str) -> Self:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str | list[dict]) -> Self:
        """Create a user message segment."""
        return cls(role="user", content=content)

    @classmethod
    def assistant(cls, content: str, function_call: dict | None = None) -> Self:
        """Create an assistant message segment, optionally with function_call."""
        return cls(role="assistant", content=content, function_call=function_call)

    @classmethod
    def tool(cls, content: str, name: str) -> Self:
        """Create a tool response message."""
        return cls(role="tool", content=content, name=name)

    @classmethod
    def assistant_call(cls, name: str, arguments: dict) -> Self:
        """
        Create an assistant message that performs a function_call.

        This instructs the model to call a function, not a tool/tool response.

        Args:
            name: Function name.
            arguments: JSON-serializable function arguments.
        """
        return cls(
            role="assistant",
            content="",
            function_call={"name": name, "arguments": json.dumps(arguments)},
        )

    @classmethod
    def image(cls, *, url: str = None, base64_data: str = None, detail: str = "auto") -> Self:
        """
        Create a user multimodal message with an image.

        Args:
            url: Public image URL (preferred).
            base64_data: Optional base64 image string.
            detail: Level of image detail.
        """
        if url and base64_data:
            raise ValueError("Provide only one of url or base64_data.")
        if not url and not base64_data:
            raise ValueError("Must provide either url or base64_data.")

        payload = {
            "type": "image_url",
            "image_url": {
                "url": url if url else f"data:image/png;base64,{base64_data}",
                "detail": detail,
            },
        }

        return cls(role="user", content=[payload])

    # --- 内容合并 ---
    def __add__(self, other: Self) -> Self | History:
        if not isinstance(other, MessageSegment):
            return NotImplemented
        if (
            self.role == other.role
            and self.name == other.name
            and self.function_call == other.function_call
        ):
            return self._merge_content_with(other)
        else:
            return History(self, other)

    def _merge_content_with(self, other: Self) -> Self:
        new_content = self._combine_content(self.content, other.content)
        return self.copy(update={"content": new_content})

    @staticmethod
    def _combine_content(c1: ContentType, c2: ContentType) -> ContentType:
        if isinstance(c1, str) and isinstance(c2, str):
            return c1 + "\n" + c2
        elif isinstance(c1, list) and isinstance(c2, list):
            return c1 + c2
        else:
            raise TypeError(f"Cannot merge content of different types: {type(c1)} vs {type(c2)}")

    # --- 验证 ---
    @field_validator("function_call")
    @classmethod
    def validate_function_call(cls, v, info):
        if v is not None and info.data.get("role") != "assistant":
            raise ValueError("function_call is only allowed when role is 'assistant'")
        return v

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        if isinstance(v, str) and not v.strip():
            raise ValueError("Content cannot be empty.")
        return v

    # --- 转换与行为 ---
    def dict_for_openai(self) -> dict:
        """Convert to OpenAI-compatible dictionary (for API call)."""
        return self.model_dump(exclude_none=True)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, MessageSegment) and self.model_dump() == other.model_dump()

    def __ne__(self, other: object) -> bool:
        return not self == other

    def __hash__(self) -> int:
        return hash(
            (
                self.role,
                json.dumps(self.content, sort_keys=True),
                self.name,
                json.dumps(self.function_call, sort_keys=True) if self.function_call else None,
            )
        )

    def __str__(self) -> str:
        return f"<{self.role}>: {self.content}"

    def __repr__(self) -> str:
        return (
            f"MessageSegment(role={self.role!r}, content={self.content!r}, "
            f"name={self.name!r}, function_call={self.function_call!r})"
        )


class History(MutableSequence[MessageSegment]):
    """
    A sequence of MessageSegment objects representing a chat history.

    Supports merging with strings (as user), MessageSegment, or another History.
    """

    def __init__(self, *messages: str | list[MessageSegment] | MessageSegment | History):
        """
        Initialize History with flexible input types.

        Args:
            *messages: Any combination of:
                - str: converted to user message
                - MessageSegment: appended directly
                - list[MessageSegment]: extended
                - History: merged from existing history
        """
        self._messages: list[MessageSegment] = []

        for message in messages:
            if isinstance(message, str):
                self.append(MessageSegment.user(message))
            elif isinstance(message, MessageSegment):
                self.append(message)
            elif isinstance(message, list) and all(isinstance(m, MessageSegment) for m in message):
                self.extend(message)
            elif isinstance(message, History):
                self.extend(message._messages)
            else:
                raise TypeError(f"Unsupported type for message: {type(message)}")

    def __getitem__(self, index: int) -> MessageSegment:
        return self._messages[index]

    def __setitem__(self, index: int, value: MessageSegment) -> None:
        self._messages[index] = value

    def __delitem__(self, index: int) -> None:
        del self._messages[index]

    def __len__(self) -> int:
        return len(self._messages)

    def insert(self, index: int, value: MessageSegment) -> None:
        self._messages.insert(index, value)

    def __iter__(self) -> Iterator[MessageSegment]:
        return iter(self._messages)

    def __add__(self, other: HistoryInput) -> History:
        """
        Add a MessageSegment, string (as user), or another History to this history.

        Args:
            other: str | MessageSegment | History

        Returns:
            New History
        """
        new_history = self.copy()
        new_history += other
        return new_history

    def __iadd__(self, other: HistoryInput) -> Self:
        """
        In-place addition of message, string, or another history.

        Args:
            other: str | MessageSegment | History

        Returns:
            Self
        """
        if isinstance(other, str):
            self.append(MessageSegment.user(other))
        elif isinstance(other, MessageSegment):
            self.append(other)
        elif isinstance(other, History):
            self._messages.extend(other._messages)
        else:
            raise TypeError(f"Unsupported type for addition: {type(other)}")
        return self

    def __radd__(self, other: HistoryInput) -> History:
        """
        Support reversed addition (e.g., str + History).

        Args:
            other: str | MessageSegment | History

        Returns:
            New History
        """
        if isinstance(other, str):
            return History([MessageSegment.user(other)]) + self
        elif isinstance(other, MessageSegment):
            return History([other]) + self
        elif isinstance(other, History):
            return other + self
        else:
            raise TypeError(f"Unsupported type for addition: {type(other)}")

    def to_list(self) -> list[dict]:
        """Convert to OpenAI-compatible list of dicts."""
        return [msg.dict_for_openai() for msg in self._messages]

    @classmethod
    def from_list(cls, messages: list[dict]) -> Self:
        """Construct History from a list of OpenAI-compatible dicts."""
        return cls([MessageSegment(**m) for m in messages])

    def copy(self) -> History:
        """Return a deep copy of the history."""
        return History(deepcopy(self._messages))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, History):
            return False
        return self.to_list() == other.to_list()

    def __ne__(self, other: object) -> bool:
        return not self == other

    def __hash__(self) -> int:
        return hash(tuple(msg.__hash__() for msg in self._messages))

    def __str__(self) -> str:
        """Human-readable string representation."""
        return "\n".join(str(msg) for msg in self._messages)

    def __repr__(self) -> str:
        return f"History({len(self._messages)} messages)"
