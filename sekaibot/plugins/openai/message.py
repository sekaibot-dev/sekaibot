from __future__ import annotations

import json
from collections.abc import Iterator, MutableSequence
from copy import deepcopy
from typing import Any, Literal, Self, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

HistoryInput = TypeVar("HistoryInput", str, list["MessageSegment"], "MessageSegment", "History")

Role = Literal["system", "user", "assistant", "tool"]
ContentType = str | list[dict]


class MessageSegment(BaseModel):
    """
    A single message used in the OpenAI Chat Completions API.

    This class encapsulates all fields required for a valid message, including:
    - tool call responses (tool_call_id)
    - function invocation requests (tool_calls)
    - multimodal messages

    Attributes:
        role (str): One of 'system', 'user', 'assistant', 'tool'.
        content (str | list[dict] | None): Message content or multimodal payload.
        name (str | None): Optional name (used for functions or tools).
        tool_call_id (str | None): Required if role is 'tool'.
        tool_calls (list[dict] | None): Required if role is 'assistant' with function calls.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Role
    content: ContentType | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict] | None = None

    # --- 构造方法 ---
    @classmethod
    def system(cls, content: ContentType) -> Self:
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: ContentType) -> Self:
        return cls(role="user", content=content)

    @classmethod
    def assistant(
        cls, content: ContentType | None = None, tool_calls: list[dict] | None = None
    ) -> Self:
        return cls(role="assistant", content=content, tool_calls=tool_calls)

    @classmethod
    def tool(cls, tool_call_id: str, content: str) -> Self:
        return cls(role="tool", tool_call_id=tool_call_id, content=content)

    @classmethod
    def assistant_tool_call(cls, *, calls: list[dict]) -> Self:
        """
        Create an assistant message that triggers tool/function calls.

        Args:
            calls: A list of tool_calls. Each must include 'id', 'type', and 'function'.

        Returns:
            MessageSegment
        """
        return cls(role="assistant", content=None, tool_calls=calls)

    @classmethod
    def image(
        cls, *, url: str | None = None, base64_data: str | None = None, detail: str = "auto"
    ) -> Self:
        """
        Create a user multimodal message with an image.

        Args:
            url: The image URL.
            base64_data: Base64 string for inline image.
            detail: Level of detail for image input ("auto", "low", "high").

        Returns:
            MessageSegment
        """
        if url and base64_data:
            raise ValueError("Provide either url or base64_data, not both.")
        if not url and not base64_data:
            raise ValueError("You must provide either url or base64_data.")

        image_url = url or f"data:image/png;base64,{base64_data}"
        return cls(
            role="user",
            content=[{"type": "image_url", "image_url": {"url": image_url, "detail": detail}}],
        )

    @field_validator("role")
    @classmethod
    def validate_role_constraints(cls, role_value: str, info: ValidationInfo) -> str:
        """
        Ensure required fields are present depending on the role type.

        - tool -> must have tool_call_id
        - assistant -> must have content or tool_calls
        """
        role: str = role_value
        data: dict[str, Any] = info.data

        if role == "tool":
            if not data.get("tool_call_id"):
                raise ValueError("tool role requires tool_call_id")
            if data.get("content") is None:
                raise ValueError("tool role requires content")
        elif role == "assistant":
            if not data.get("content") and not data.get("tool_calls"):
                raise ValueError("assistant must provide content or tool_calls")
        elif role in {"system", "user"}:
            if data.get("content") is None:
                raise ValueError(f"{role} role requires non-empty content")

        return role

    @field_validator("tool_calls")
    @classmethod
    def validate_tool_calls(
        cls, tool_calls: list[dict] | None, info: ValidationInfo
    ) -> list[dict] | None:
        """
        Validate that tool_calls only appear when role is 'assistant'.
        """
        role: str | None = info.data.get("role")
        if tool_calls is not None and role != "assistant":
            raise ValueError("tool_calls is only allowed when role is 'assistant'")
        return tool_calls

    @field_validator("tool_call_id")
    @classmethod
    def validate_tool_call_id(cls, tool_call_id: str | None, info: ValidationInfo) -> str | None:
        """
        Validate that tool_call_id only appears when role is 'tool'.
        """
        role: str | None = info.data.get("role")
        if tool_call_id is not None and role != "tool":
            raise ValueError("tool_call_id is only allowed when role is 'tool'")
        return tool_call_id

    @field_validator("content")
    @classmethod
    def validate_content(cls, content: Any, info: ValidationInfo) -> Any:
        """
        Ensure that content is not missing where required.

        Assistant can omit content only if tool_calls are provided.
        All other roles must have non-empty content.
        """
        role: str | None = info.data.get("role")

        if role == "assistant" and content is None and info.data.get("tool_calls") is None:
            raise ValueError("Assistant must provide either content or tool_calls")

        if role != "assistant" and content is None:
            raise ValueError(f"Content cannot be None for role '{role}'")

        if isinstance(content, str) and not content.strip():
            raise ValueError("Content cannot be empty string")

        return content

    def __add__(self, other: Self) -> Self | History:
        if not isinstance(other, MessageSegment):
            return NotImplemented
        if (
            self.role == other.role
            and self.name == other.name
            and self.tool_call_id == other.tool_call_id
            and self.tool_calls == other.tool_calls
        ):
            return self._merge_content_with(other)
        else:
            return History(self, other)

    def _merge_content_with(self, other: Self) -> Self:
        new_content = self._combine_content(self.content, other.content)
        return self.copy(update={"content": new_content})

    @staticmethod
    def _combine_content(c1: ContentType | None, c2: ContentType | None) -> ContentType:
        if c1 is None or c2 is None:
            raise TypeError("Cannot merge messages with None content")
        if isinstance(c1, str) and isinstance(c2, str):
            return c1 + "\n" + c2
        elif isinstance(c1, list) and isinstance(c2, list):
            return c1 + c2
        else:
            raise TypeError(f"Cannot merge content of different types: {type(c1)} vs {type(c2)}")

    def dict_for_openai(self) -> dict:
        """
        Convert the message to OpenAI SDK-compliant dictionary.

        Returns:
            dict
        """
        return self.model_dump(exclude_none=True)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MessageSegment):
            return False
        return self.model_dump() == other.model_dump()

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(
            (
                self.role,
                json.dumps(self.content, sort_keys=True) if self.content is not None else None,
                self.name,
                self.tool_call_id,
                json.dumps(self.tool_calls, sort_keys=True) if self.tool_calls else None,
            )
        )

    def __str__(self) -> str:
        return f"<{self.role}>: {self.content}"

    def __repr__(self) -> str:
        return (
            f"MessageSegment(role={self.role!r}, content={self.content!r}, "
            f"name={self.name!r}, tool_call_id={self.tool_call_id!r}, tool_calls={self.tool_calls!r})"
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
