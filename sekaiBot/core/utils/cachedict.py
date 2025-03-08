import time
from collections import OrderedDict
from collections.abc import MutableMapping
from typing import TypeVar, Generic, Optional

# **定义泛型**
K = TypeVar("K")  # 键类型
V = TypeVar("V")  # 值类型

class cacheDict(MutableMapping, Generic[K, V]):
    """支持类型标注的 LRU 缓存"""

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        self.data: OrderedDict[K, tuple[V, float]] = OrderedDict()  # 存储值和时间戳

    def __setitem__(self, key: K, value: V) -> None:
        """设置键值，并更新活跃度"""
        if key in self.data:
            self.data.move_to_end(key)  # 访问的键移动到末尾
        elif len(self.data) >= self.max_size:
            self.data.popitem(last=False)  # 删除最久未访问的键
        self.data[key] = (value, time.time())  # 存储值和时间戳

    def __getitem__(self, key: K) -> V:
        """访问键，更新访问时间"""
        if key in self.data:
            value, _ = self.data.pop(key)
            self[key] = value  # 重新存储，变成最近访问的键
            return value
        raise KeyError(f"{key} 不存在")

    def get(self, key: K, default: Optional[V] = None) -> Optional[V]:
        """获取键值，若不存在返回 default"""
        try:
            return self[key]
        except KeyError:
            return default

    def __delitem__(self, key: K) -> None:
        """删除键"""
        if key in self.data:
            del self.data[key]
        else:
            raise KeyError(f"{key} 不存在")

    def __contains__(self, key: K) -> bool:
        """判断键是否存在"""
        return key in self.data

    def __len__(self) -> int:
        """返回缓存大小"""
        return len(self.data)

    def __iter__(self):
        """返回键的迭代器"""
        return iter(self.data)

    def __repr__(self) -> str:
        """返回可见数据"""
        return str({k: v[0] for k, v in self.data.items()})
