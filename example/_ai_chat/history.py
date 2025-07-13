import asyncio
import json
from collections import OrderedDict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, messages_from_dict, messages_to_dict


class ChatMessageHistory(BaseChatMessageHistory):
    """Chat message history that stores history in a local file."""

    def __init__(
        self,
        file_path: str,
        *,
        max_len: int | None = None,
        encoding: str | None = None,
        ensure_ascii: bool = True,
    ) -> None:
        """Initialize the file path for the chat history.

        Args:
            file_path: The path to the local file to store the chat history.
            encoding: The encoding to use for file operations. Defaults to None.
            ensure_ascii: If True, escape non-ASCII in JSON. Defaults to True.
        """
        self.file_path = Path(file_path)
        self.max_len = max_len
        self.encoding = encoding
        self.ensure_ascii = ensure_ascii

        if not self.file_path.exists():
            self.file_path.touch()
            self.file_path.write_text(
                json.dumps([], ensure_ascii=self.ensure_ascii), encoding=self.encoding
            )

    @property
    def messages(self) -> list[BaseMessage]:  # type: ignore
        """Retrieve the messages from the local file"""
        items = json.loads(self.file_path.read_text(encoding=self.encoding))
        return messages_from_dict(items)

    def add_message(self, message: BaseMessage) -> None:
        """Append the message to the record in the local file"""
        messages = messages_to_dict(self.messages)
        messages.append(messages_to_dict([message])[0])
        if self.max_len and len(messages) > self.max_len:
            messages = messages[-self.max_len:]
        self.file_path.write_text(
            json.dumps(messages, ensure_ascii=self.ensure_ascii), encoding=self.encoding
        )

    def clear(self) -> None:
        """Clear session memory from the local file"""
        self.file_path.write_text(
            json.dumps([], ensure_ascii=self.ensure_ascii), encoding=self.encoding
        )


class AsyncPersistentLRUDict:
    """文件储存缓存"""
    _data: OrderedDict[str, str]

    def __init__(self, file_path: str, max_len: int | None = None):
        self.file = Path(file_path)
        self.max_len = max_len
        self._data = OrderedDict()  # key 顺序 = LRU
        self._lock = asyncio.Lock()
        self._load()

    def _load(self) -> None:
        if self.file.exists():
            try:
                with self.file.open("r", encoding="utf-8") as f:
                    raw = json.load(f)
                    self._data = OrderedDict(raw)
            except Exception as e:
                print(f"加载文件失败：{e}")
                self._data = OrderedDict()

    async def _save(self) -> None:
        async with self._lock:
            tmp_file = self.file.with_suffix(".tmp")
            with tmp_file.open("w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False)
            tmp_file.replace(self.file)

    async def set(self, key: str, value: str) -> None:
        async with self._lock:
            if key in self._data:
                del self._data[key]  # 删除旧位置
            self._data[key] = value  # 插入末尾（最新）
            await self._trim()
        await self._save()

    async def get(self, key: str, default: Any | None = None) -> str | None:
        async with self._lock:
            value = self._data.get(key, default)
            if key in self._data:
                # 刷新 LRU：移到末尾
                self._data.move_to_end(key)
        return value

    async def pop(self, key: str) -> None:
        async with self._lock:
            if key in self._data:
                self._data.pop(key)
                await self._save()

    async def keys(self) -> Iterable[str]:
        async with self._lock:
            return self._data.keys()

    async def values(self) -> Iterable[str]:
        async with self._lock:
            return self._data.values()

    async def items(self) -> Iterable[tuple[str, str]]:
        async with self._lock:
            return self._data.items()

    async def __len__(self) -> int:
        async with self._lock:
            return len(self._data)

    async def __contains__(self, key: str) -> bool:
        async with self._lock:
            return key in self._data

    async def _trim(self) -> None:
        if self.max_len:
            while len(self._data) > self.max_len:
                self._data.popitem(last=False)

    async def __getitem__(self, key: str) -> str | None:
        value = await self.get(key)
        if value is None:
            raise KeyError(f"Key {key} 不存在")
        return value

    async def __setitem__(self, key: str, value: str) -> None:
        await self.set(key, value)
