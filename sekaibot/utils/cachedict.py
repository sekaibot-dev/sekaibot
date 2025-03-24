import time
from collections import OrderedDict
from collections.abc import Iterator, MutableMapping
from typing import Generic, TypeVar

# **定义泛型**
K = TypeVar("K")  # 键类型
V = TypeVar("V")  # 值类型


class LRUCache(MutableMapping, Generic[K, V]):
    """
    支持类型标注的 LRU（Least Recently Used）缓存。

    维护键值对，并在超过最大容量时，淘汰最近最少使用的键。
    """

    __slots__ = ("max_size", "data")

    def __init__(self, max_size: int = 100) -> None:
        """
        初始化 LRU 缓存。

        Args:
            max_size: 最大缓存容量，超出后会淘汰最久未使用的项。
        """
        self.max_size = max_size
        self.data: OrderedDict[K, tuple[V, float]] = OrderedDict()

    def __setitem__(self, key: K, value: V) -> None:
        """
        设置键值，并更新其活跃度。

        Args:
            key: 要设置的键。
            value: 要设置的值。
        """
        if key in self.data:
            self.data.move_to_end(key)
        elif len(self.data) >= self.max_size:
            self.data.popitem(last=False)
        self.data[key] = (value, time.time())

    def __getitem__(self, key: K) -> V:
        """
        获取键值，并更新其活跃度。

        Args:
            key: 要获取的键。

        Returns:
            对应的值。

        Raises:
            KeyError: 如果键不存在。
        """
        if key in self.data:
            value, _ = self.data.pop(key)
            self[key] = value
            return value
        raise KeyError(f"{key} 不存在")

    def get(self, key: K, default: V | None = None) -> V | None:
        """
        获取键值，若不存在则返回默认值。

        Args:
            key: 要获取的键。
            default: 如果键不存在，返回的默认值。

        Returns:
            键对应的值或默认值。
        """
        try:
            return self[key]
        except KeyError:
            return default

    def __delitem__(self, key: K) -> None:
        """
        删除指定键。

        Args:
            key: 要删除的键。

        Raises:
            KeyError: 如果键不存在。
        """
        if key in self.data:
            del self.data[key]
        else:
            raise KeyError(f"{key} 不存在")

    def __contains__(self, key: K) -> bool:
        """
        判断键是否存在。

        Args:
            key: 要判断的键。

        Returns:
            是否存在。
        """
        return key in self.data

    def __len__(self) -> int:
        """
        获取当前缓存大小。

        Returns:
            缓存中的键值数量。
        """
        return len(self.data)

    def __iter__(self) -> Iterator[K]:
        """
        返回键的迭代器。

        Returns:
            可迭代对象。
        """
        return iter(self.data)

    def __repr__(self) -> str:
        """
        获取当前缓存的可读表示。

        Returns:
            字符串表示。
        """
        return f"{self.__class__.__name__}({{ {', '.join(f'{k!r}: {v[0]!r}' for k, v in self.data.items())} }})"


class TTLCache(MutableMapping, Generic[K, V]):
    """
    支持 TTL（Time To Live）的缓存，键值对会在指定时间后自动过期。
    """

    __slots__ = ("_ttl", "_data")

    def __init__(self, ttl: float = 60.0) -> None:
        """
        初始化 TTL 缓存。

        Args:
            ttl: 每个键值对的生存时间（秒）。
        """
        self._ttl = ttl
        self._data: dict[K, tuple[V, float]] = {}

    def __setitem__(self, key: K, value: V) -> None:
        """
        设置键值，记录插入时间。

        Args:
            key: 要设置的键。
            value: 要设置的值。
        """
        self._data[key] = (value, time.time())

    def __getitem__(self, key: K) -> V:
        """
        获取键值，如果已过期则删除并抛出 KeyError。

        Args:
            key: 要获取的键。

        Returns:
            对应的值。

        Raises:
            KeyError: 如果键不存在或已过期。
        """
        if key in self._data:
            value, timestamp = self._data[key]
            if time.time() - timestamp <= self._ttl:
                return value
            else:
                del self._data[key]
        raise KeyError(f"{key} 不存在或已过期")

    def get(self, key: K, default: V | None = None) -> V | None:
        """
        获取键值，若不存在或已过期则返回默认值。

        Args:
            key: 要获取的键。
            default: 如果键不存在或过期，返回的默认值。

        Returns:
            键对应的值或默认值。
        """
        try:
            return self[key]
        except KeyError:
            return default

    def __delitem__(self, key: K) -> None:
        """
        删除指定键。

        Args:
            key: 要删除的键。

        Raises:
            KeyError: 如果键不存在。
        """
        if key in self._data:
            del self._data[key]
        else:
            raise KeyError(f"{key} 不存在")

    def __contains__(self, key: K) -> bool:
        """
        判断键是否存在且未过期。

        Args:
            key: 要判断的键。

        Returns:
            是否存在且未过期。
        """
        if key in self._data:
            _, timestamp = self._data[key]
            if time.time() - timestamp <= self._ttl:
                return True
            else:
                del self._data[key]
        return False

    def __len__(self) -> int:
        """
        获取当前未过期的键数量。

        Returns:
            当前缓存中有效键的数量。
        """
        self._expire_all()
        return len(self._data)

    def __iter__(self) -> Iterator[K]:
        """
        返回未过期键的迭代器。

        Returns:
            可迭代对象。
        """
        self._expire_all()
        return iter(self._data)

    def __repr__(self) -> str:
        """
        获取当前缓存的可读表示。

        Returns:
            字符串表示。
        """
        self._expire_all()
        return f"{self.__class__.__name__}({{ {', '.join(f'{k!r}: {v[0]!r}' for k, v in self._data.items())} }})"

    def _expire_all(self) -> None:
        """内部方法：清除所有过期项。"""
        now = time.time()
        keys_to_remove = [k for k, (_, ts) in self._data.items() if now - ts > self._ttl]
        for k in keys_to_remove:
            del self._data[k]
