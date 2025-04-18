from __future__ import annotations

import json
from collections.abc import Iterable
from copy import deepcopy
from typing import Any, Literal, Self, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    GetCoreSchemaHandler,
    ValidationInfo,
    field_validator,
    model_validator,
)
from pydantic_core import core_schema

HistoryInput = TypeVar("HistoryInput", str, list["MessageSegment"], "MessageSegment", "History")

Role = Literal["system", "user", "assistant", "tool"]
ContentType = str | list[dict]


class MessageSegment(BaseModel):
    """A single message used in the OpenAI Chat Completions API.

    This class encapsulates all fields required for a valid message, including:
    - tool call responses (`tool_call_id`)
    - tool/function invocation requests (`tool_calls`)
    - multimodal image messages

    Attributes:
        role: One of 'system', 'user', 'assistant', 'tool'.
        content: Text or multimodal content (or None for tool_calls).
        name: Optional name used for function/tool definitions.
        tool_call_id: Required if role is 'tool'.
        tool_calls: Required if role is 'assistant' making tool calls.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Role
    content: ContentType | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict] | None = None

    def __str__(self) -> str:
        """Human-readable string representation of the message segment.

        Returns:
            A string showing the role and either content or tool_calls.
        """
        if self.role == "assistant" and self.tool_calls:
            return f"<assistant>: tool_calls={self.tool_calls}"
        return f"<{self.role}>: {self.content}"

    def __repr__(self) -> str:
        return (
            f"MessageSegment(role={self.role!r}, content={self.content!r}, "
            f"name={self.name!r}, tool_call_id={self.tool_call_id!r}, tool_calls={self.tool_calls!r})"
        )

    @classmethod
    def system(cls, content: ContentType) -> Self:
        """Create a system message.

        Args:
            content: Instructional content.

        Returns:
            MessageSegment
        """
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: ContentType) -> Self:
        """Create a user message.

        Args:
            content: User's input or query.

        Returns:
            MessageSegment
        """
        return cls(role="user", content=content)

    @classmethod
    def assistant(
        cls, content: ContentType | None = None, tool_calls: list[dict] | None = None
    ) -> Self:
        """Create an assistant message.

        Args:
            content: Assistant's textual response.
            tool_calls: List of tool call requests.

        Returns:
            MessageSegment
        """
        return cls(role="assistant", content=content, tool_calls=tool_calls)

    @classmethod
    def tool(cls, tool_call_id: str, content: str) -> Self:
        """Create a tool message in response to a specific tool call.

        Args:
            tool_call_id: ID of the tool call being responded to.
            content: The tool's response content.

        Returns:
            MessageSegment
        """
        return cls(role="tool", tool_call_id=tool_call_id, content=content)

    @classmethod
    def assistant_tool_call(cls, *, calls: list[dict]) -> Self:
        """Create an assistant message that issues tool/function calls.

        Args:
            calls: A list of tool call objects. Each must include 'id', 'type', and 'function'.

        Returns:
            MessageSegment
        """
        return cls(role="assistant", content=None, tool_calls=calls)

    @classmethod
    def image(
        cls, *, url: str | None = None, base64_data: str | None = None, detail: str = "auto"
    ) -> Self:
        """Create a multimodal user message with an image.

        Args:
            url: Public or signed image URL.
            base64_data: Base64-encoded inline image.
            detail: Detail level ("auto", "low", "high").

        Returns:
            MessageSegment

        Raises:
            ValueError: If neither or both url and base64_data are provided.
        """
        if url and base64_data:
            raise ValueError("Provide either url or base64_data, not both.")
        if not url and not base64_data:
            raise ValueError("You must provide either url or base64_data.")

        image_url = url or f"data:image/jpeg;base64,{base64_data}"
        return cls(
            role="user",
            content=[{"type": "image_url", "image_url": {"url": image_url, "detail": detail}}],
        )

    @model_validator(mode="after")
    def validate_role_and_fields(self) -> Self:
        """Validate required fields based on role after full model construction.

        - tool -> must have tool_call_id
        - assistant -> must have content or tool_calls

        Returns:
            Self

        Raises:
            ValueError: If required fields are missing based on role.
        """
        if self.role == "tool":
            if not self.tool_call_id:
                raise ValueError("tool role requires tool_call_id")
            if self.content is None:
                raise ValueError("tool role requires content")

        elif self.role == "assistant":
            if self.content is None and not self.tool_calls:
                raise ValueError("assistant must provide either content or tool_calls")

        elif self.role in {"system", "user"}:
            if self.content is None:
                raise ValueError(f"{self.role} role requires non-empty content")
            if isinstance(self.content, str) and not self.content.strip():
                raise ValueError("Content cannot be empty string")

        return self

    @field_validator("tool_calls")
    @classmethod
    def validate_tool_calls(
        cls, tool_calls: list[dict] | None, info: ValidationInfo
    ) -> list[dict] | None:
        """Validate that tool_calls only appear when role is 'assistant'.

        Args:
            tool_calls: Value of the field.
            info: Validation context.

        Returns:
            The validated tool_calls list or None.

        Raises:
            ValueError: If role is not assistant.
        """
        role: str | None = info.data.get("role")
        if tool_calls is not None and role != "assistant":
            raise ValueError("tool_calls is only allowed when role is 'assistant'")
        return tool_calls

    @field_validator("tool_call_id")
    @classmethod
    def validate_tool_call_id(cls, tool_call_id: str | None, info: ValidationInfo) -> str | None:
        """Validate that tool_call_id only appears when role is 'tool'.

        Args:
            tool_call_id: ID value.
            info: Validation context.

        Returns:
            The validated tool_call_id or None.

        Raises:
            ValueError: If role is not 'tool'.
        """
        role: str | None = info.data.get("role")
        if tool_call_id is not None and role != "tool":
            raise ValueError("tool_call_id is only allowed when role is 'tool'")
        return tool_call_id

    @field_validator("content")
    @classmethod
    def validate_content(cls, content: Any, info: ValidationInfo) -> Any:
        """Validate content field presence and type.

        Args:
            content: Message content.
            info: Validation context.

        Returns:
            The validated content.

        Raises:
            ValueError: If content is missing or empty where required.
        """
        role: str | None = info.data.get("role")

        if role == "assistant" and content is None and info.data.get("tool_calls") is None:
            raise ValueError("Assistant must provide either content or tool_calls")
        if role != "assistant" and content is None:
            raise ValueError(f"Content cannot be None for role '{role}'")
        if content is not None and not isinstance(content, str | list):
            raise ValueError("Content must be a string or a list of dictionaries")
        if isinstance(content, str) and not content.strip():
            raise ValueError("Content cannot be empty string")

        return content

    def __add__(self, other: Self | History) -> Self | History:
        """Support addition for merging or history composition."""
        if isinstance(other, MessageSegment):
            if (
                self.role == other.role
                and self.name == other.name
                and self.tool_call_id == other.tool_call_id
                and self.tool_calls == other.tool_calls
            ):
                return self._merge_content_with(other)
            else:
                return History(self, other)
        elif isinstance(other, History):
            return History(self, other)
        
    def __radd__(self, other: Self | History) -> Self | History:
        """Support reversed addition."""
        if isinstance(other, MessageSegment):
            return other.__add__(self)
        elif isinstance(other, History):
            return History(other).__add__(self)
        else:
            raise TypeError(f"Unsupported type for addition: {type(other)}")

    def _merge_content_with(self, other: Self) -> Self:
        """Internal method to merge message contents."""
        new_content = self._combine_content(self.content, other.content)
        return self.model_copy(update={"content": new_content})

    @staticmethod
    def _combine_content(c1: ContentType | None, c2: ContentType | None) -> ContentType:
        """Combine two message content blocks."""

        def format_content(c: str):
            return [{"type": "text", "text": c}]

        c1 = format_content(c1) if isinstance(c1, str) else c1 if c1 else []
        c2 = format_content(c2) if isinstance(c2, str) else c2 if c2 else []
        return c1 + c2

    def dict_for_openai(self) -> dict:
        """Convert message to OpenAI API-compliant dict.

        Returns:
            A JSON-serializable message dict.
        """
        return self.model_dump(exclude_none=True)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, MessageSegment) and self.model_dump() == other.model_dump()

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


class History(list[MessageSegment]):
    """A sequence of MessageSegment objects representing a chat history.

    This class behaves like a standard list of MessageSegment while providing
    additional convenience methods to work with OpenAI Chat Completions API.

    Examples:
        >>> History("Hi", MessageSegment.assistant("Hello"))
        >>> History.from_list(openai_messages)

    Args:
        *messages: One or more message inputs:
            - str: converted to MessageSegment.user(...)
            - MessageSegment
            - list[MessageSegment]
            - History
    """

    def __init__(self, *messages: str | list[MessageSegment] | MessageSegment | History):
        super().__init__()
        for message in messages:
            if isinstance(message, str):
                self.append(MessageSegment.user(message))
            elif isinstance(message, MessageSegment):
                self.append(message)
            elif isinstance(message, list) and all(isinstance(m, MessageSegment) for m in message):
                self.extend(message)
            elif isinstance(message, History):
                self.extend(message)
            else:
                raise TypeError(f"Unsupported type for message: {type(message)}")

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source: type[Any], handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Custom schema definition to support both History and list[MessageSegment]."""
        return core_schema.union_schema(
            [
                core_schema.is_instance_schema(cls),
                core_schema.no_info_after_validator_function(
                    # cls,
                    # handler.generate_schema(list[MessageSegment]),
                    function=cls.from_list,
                    schema=handler.generate_schema(list[dict]),
                ),
            ]
        )

    def __str__(self) -> str:
        """Return a human-readable string of the history.

        Returns:
            A newline-joined string of message summaries.
        """
        return "\n".join(str(msg) for msg in self)

    def __repr__(self) -> str:
        """Return debug representation.

        Returns:
            Summary of History object.
        """
        return f"History({len(self)} messages)"

    def reduce(self) -> History:
        """Reduce the history by merging consecutive compatible messages.

        If adjacent messages can be merged (same role, same metadata), they will
        be combined using MessageSegment.__add__.

        Returns:
            A new History instance with reduced (merged) messages.
        """
        if not self:
            return History()

        reduced: list[MessageSegment] = [self[0]]

        for msg in self[1:]:
            last = reduced[-1]
            merged = last + msg

            if isinstance(merged, MessageSegment):
                reduced[-1] = merged
            else:
                reduced.append(msg)

        return History(*reduced)

    def _append(self, message: MessageSegment) -> None:
        """Append a message with intelligent merging if compatible.

        Args:
            message: A MessageSegment to add.
        """
        if not isinstance(message, MessageSegment):
            raise TypeError(f"Expected MessageSegment, got {type(message)}")

        if self and isinstance(self[-1], MessageSegment):
            merged = self[-1] + message
            if isinstance(merged, MessageSegment):
                self[-1] = merged
                return
        self.append(message)

    def _extend(self, values: Iterable[MessageSegment]) -> None:
        """Extend history with iterable of messages using merge-aware append.

        Args:
            values: Iterable of MessageSegment objects.
        """
        for message in values:
            self._append(message)

    def __add__(self, other: str | MessageSegment | History) -> History:
        """Return a new History with the other item(s) added.

        Args:
            other: The message(s) to add.

        Returns:
            A new History instance.
        """
        return History(*self).__iadd__(other)

    def __iadd__(self, other: str | MessageSegment | History) -> Self:
        """In-place addition of new message(s).

        Args:
            other: The message(s) to add.

        Returns:
            The updated History instance.
        """
        if isinstance(other, str):
            self._append(MessageSegment.user(other))
        elif isinstance(other, MessageSegment):
            self._append(other)
        elif isinstance(other, History):
            self._extend(other)
        else:
            raise TypeError(f"Unsupported type for addition: {type(other)}")
        return self

    def __radd__(self, other: str | MessageSegment | History) -> History:
        """Support reversed addition (e.g., str + History).

        Args:
            other: The message(s) to add before this history.

        Returns:
            A new History instance.
        """
        if isinstance(other, str):
            return History(MessageSegment.user(other))._extend(self)
        elif isinstance(other, MessageSegment):
            return History(other)._extend(self)
        elif isinstance(other, History):
            return other._extend(self)
        else:
            raise TypeError(f"Unsupported type for addition: {type(other)}")

    def to_list(self) -> list[dict]:
        """Convert to OpenAI-compatible list of message dictionaries.

        Returns:
            A list of OpenAI-ready dict messages.
        """
        return [msg.dict_for_openai() for msg in self]

    @classmethod
    def from_list(cls, messages: list[dict]) -> Self:
        """Create a History instance from OpenAI-format message dicts.

        Args:
            messages: List of message dictionaries.

        Returns:
            A History instance.
        """
        return cls(*[MessageSegment(**m) for m in messages])

    def copy(self) -> History:
        """Return a deep copy of the History.

        Returns:
            A cloned History instance.
        """
        return History(*deepcopy(self))

    def last(self, n: int) -> History:
        """Return the last `n` messages as a new History.

        Args:
            n: Number of most recent messages to return.

        Returns:
            A new History containing the last `n` items.
        """
        return History(*self[-n:])

    def filter(self, *, role: Role) -> History:
        """Return a new History with messages matching the given role.

        Args:
            role: One of 'user', 'assistant', 'system', 'tool'.

        Returns:
            A filtered History.
        """
        return History(*[msg for msg in self if msg.role == role])


if __name__ == "__main__":
    # Example usage

    msg = (
        MessageSegment.user("Hello, how are you?")
        + MessageSegment.assistant("I'm good, thank you!")
        + MessageSegment.image(url="http://example.com/image.png", detail="high")
        + MessageSegment.user("What do you think?")
        + MessageSegment.assistant("I'm good, thank you!")
        + MessageSegment.assistant("I think it's a nice image.")
    )
    print(msg, "\n")

    class Example(BaseModel):
        messages: History

    e = Example(
        messages=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi! How can I help you?"},
            {
                "role": "assistant",
                "tool_calls": [{"id": "abc123", "type": "function", "function": {}}],
            },
            {"role": "tool", "tool_call_id": "abc123", "content": "22°C in Paris"},
        ]
    )

    print(e.messages)
    print(e.messages.to_list())
