"""一个简单的计数器方法

用于 Rule 的 Counter 方法
"""

import json
import time as time_util
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from typing import Any, Generic, Self, TypeVar
from typing_extensions import override

_T = TypeVar("_T")


@dataclass(frozen=True)
class RecordedEvent(Generic[_T]):
    """表示记录的事件及其属性。"""

    event: _T
    matched: bool
    timestamp: float


class Counter(Generic[_T]):
    """简单易用的事件计数器：支持时间窗口、数量窗口命中分析及合并、导出、还原等功能。"""

    __slots__ = ("_events", "_max_size", "_time")

    def __init__(
        self,
        max_size: int | None = None,
        *,
        time_func: Callable[[], float] = time_util.time,
    ) -> None:
        """初始化事件计数器。

        Args:
            max_size: 最大记录数。
            time_func: 用于生成时间戳的函数 (默认使用 time.time) 。
        """
        self._events: deque[RecordedEvent[_T]] = deque(maxlen=max_size)
        self._time = time_func
        self._max_size = max_size

    def record(
        self, event: _T, matched: bool = False, timestamp: float | None = None
    ) -> None:
        """同步记录事件，并保持时间升序。

        Args:
            event: 要记录的事件。
            matched: 是否命中。
            timestamp: 可选的时间戳 (默认为当前时间) 。
        """
        ts = timestamp if timestamp is not None else self._time()
        new_event = RecordedEvent(event, matched, ts)

        # 快速 append
        self._events.append(new_event)

        # 如果破坏了时间顺序，仅在必要时排序修复
        if len(self._events) > 1 and self._events[-2].timestamp > ts:
            self._events = deque(
                sorted(self._events, key=lambda e: e.timestamp), maxlen=self._max_size
            )

    async def arecord(
        self, event: _T, matched: bool = False, timestamp: float | None = None
    ) -> None:
        """异步记录事件。

        Args:
            event: 要记录的事件。
            matched: 是否命中。
            timestamp: 可选的自定义时间戳。
        """
        self.record(event, matched, timestamp)

    def pop(self) -> RecordedEvent[_T]:
        """弹出最新的事件。"""
        return self._events.pop()

    def popleft(self) -> RecordedEvent[_T]:
        """弹出最早的事件。"""
        return self._events.popleft()

    def count_in_time(self, seconds: float, now: float | None = None) -> int:
        """统计过去 seconds 秒内的命中次数。

        Args:
            seconds: 时间窗口 (秒) 。
            now: 可选的当前时间。

        Returns:
            命中事件数量。
        """
        now = now if now is not None else self._time()
        return sum(
            1 for e in self._events if e.matched and now - seconds <= e.timestamp < now
        )

    def count_in_latest(self, n: int) -> int:
        """统计最近 n 条记录中的命中次数。

        Args:
            n: 数量窗口大小。

        Returns:
            命中事件数量。
        """
        return sum(1 for e in list(self._events)[-n:] if e.matched)

    def count_matched(self) -> int:
        """获取命中事件总数。

        Returns:
            命中事件数。
        """
        return sum(1 for e in self._events if e.matched)

    def match_ratio(self) -> float:
        """命中率。

        Returns:
            命中事件数量 / 总事件数量。
        """
        total = len(self._events)
        return self.count_matched() / total if total > 0 else 0.0

    def latest(self) -> RecordedEvent[_T] | None:
        """获取最近的事件。

        Returns:
            最近的 RecordedEvent，或 None。
        """
        return self._events[-1] if self._events else None

    def iter_in_time(self, seconds: float, now: float | None = None) -> Iterator[_T]:
        """迭代过去 seconds 秒内的事件。

        Args:
            seconds: 时间窗口 (秒) 。
            now: 可选的当前时间。

        Returns:
            事件迭代器。
        """
        now = now if now is not None else self._time()
        return (
            e.event
            for e in self._events
            if e.matched and now - seconds <= e.timestamp < now
        )

    def iter_in_latest(self, n: int) -> Iterator[_T]:
        """迭代最近 n 条记录中的事件。

        Args:
            n: 数量窗口大小。

        Returns:
            事件迭代器。
        """
        return (e.event for e in list(self._events)[-n:] if e.matched)

    def iter_matched(self) -> Iterator[_T]:
        """迭代所有命中事件。

        Returns:
            命中事件的迭代器。
        """
        return (e.event for e in self._events if e.matched)

    def snapshot(self) -> list[dict[str, Any]]:
        """获取事件记录快照 (可序列化形式) 。

        Returns:
            当前记录的 JSON 结构列表。
        """
        return [asdict(e) for e in self._events]

    def load_snapshot(self, data: list[dict[str, Any]]) -> None:
        """从 snapshot 数据中恢复事件。

        Args:
            data: snapshot 返回的数据结构。
        """
        events = [RecordedEvent(**e) for e in data]
        events.sort(key=lambda e: e.timestamp)
        self._events.clear()
        self._events.extend(events)

    def to_json(self) -> str:
        """导出当前记录为 JSON 字符串。

        Returns:
            JSON 字符串。
        """
        return json.dumps(self.snapshot(), ensure_ascii=False)

    def clear(self) -> None:
        """清空所有记录。"""
        self._events.clear()

    def compress(self) -> None:
        """压缩事件，仅保留命中事件与最新一条。"""
        latest = self.latest()
        matched_events = [e for e in self._events if e.matched]
        self._events.clear()
        self._events.extend(matched_events)
        if latest and latest not in self._events:
            self._events.append(latest)

    def copy(self) -> "Counter[_T]":
        """复制当前事件计数器。"""
        copied = Counter[_T](max_size=self._max_size, time_func=self._time)
        copied._events.extend(self._events)
        return copied

    def __len__(self) -> int:
        """获取长度"""
        return len(self._events)

    def __contains__(self, event: _T) -> bool:
        """in方法"""
        return event in self._events

    def __iter__(self) -> Iterator[RecordedEvent[_T]]:
        """iter方法"""
        return iter(self._events)

    def __reversed__(self) -> Iterator[RecordedEvent[_T]]:
        """reversed方法"""
        return reversed(self._events)

    @override
    def __repr__(self) -> str:
        return (
            f"<EventCounter(size={len(self)}, matched={self.count_matched()}, "
            f"ratio={self.match_ratio():.2%})>"
        )

    def __add__(self, other: "Counter[_T]") -> "Counter[_T]":
        """合并两个事件计数器。

        Args:
            other: 另一个事件计数器。

        Returns:
            新的合并后的 EventCounter。
        """
        merged = Counter[_T](max_size=self._max_size, time_func=self._time)
        merged._events.extend(
            sorted(list(self._events) + list(other._events), key=lambda e: e.timestamp)
        )
        return merged

    def __iadd__(self, other: "Counter[_T]") -> Self:
        """就地合并事件计数器。

        Args:
            other: 要合并的计数器。

        Returns:
            自身。
        """
        self._events.extend(other._events)
        self._events = deque(
            sorted(self._events, key=lambda e: e.timestamp), maxlen=self._max_size
        )
        return self
