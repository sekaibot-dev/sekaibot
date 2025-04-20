import time

import pytest

from sekaibot.utils.cachedict import LRUCache, TTLCache


def test_lru_cache_basic_set_get():
    cache = LRUCache[int, str](max_size=2)
    cache["a"] = "A"
    cache["b"] = "B"
    assert cache["a"] == "A"
    # 'b' and 'a' should now be in cache, 'b' least recently used
    cache["c"] = "C"
    # max_size 2, so 'b' should be evicted
    assert "b" not in cache
    assert cache.get("b") is None
    # a and c remain
    assert cache["c"] == "C"
    assert cache["a"] == "A"


def test_lru_cache_contains_len_iter_repr():
    cache = LRUCache[int, int](max_size=3)
    cache[1] = 1
    cache[2] = 2
    assert 1 in cache
    assert len(cache) == 2
    # __iter__ yields keys
    keys = list(iter(cache))
    assert keys == [1, 2]
    # __repr__ contains existing keys
    r = repr(cache)
    assert "1: 1" in r and "2: 2" in r


def test_lru_cache_keyerror():
    cache = LRUCache[str, str](max_size=1)
    with pytest.raises(KeyError):
        _ = cache["missing"]


def test_ttl_cache_expiration(monkeypatch):
    # control time
    fake_time = 1000.0

    def time_func():
        return fake_time

    cache = TTLCache[str, int](ttl=5.0)
    monkeypatch.setattr(time, "time", time_func)
    cache["x"] = 42
    assert cache["x"] == 42
    assert "x" in cache
    # advance time beyond ttl
    fake_time += 6.0
    with pytest.raises(KeyError):
        _ = cache["x"]
    assert cache.get("x") is None
    assert "x" not in cache


def test_ttl_cache_len_iter_repr():
    # shorter TTL for test
    cache = TTLCache[int, int](ttl=0.1)
    cache[1] = 10
    cache[2] = 20
    # wait for expiration
    time.sleep(0.2)
    assert len(cache) == 0
    assert list(iter(cache)) == []
    r = repr(cache)
    assert "TTLCache" in r
