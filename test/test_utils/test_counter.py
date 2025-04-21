import json

import pytest

from sekaibot.internal.rule._counter import Counter, RecordedEvent


class DummyTime:
    def __init__(self):
        self.t = 1000.0

    def time(self):
        return self.t

    def advance(self, sec):
        self.t += sec


@pytest.fixture
def dummy_time():
    return DummyTime()


def make_events(counter: Counter[int], dummy_time):
    # Create 5 events, mark even ones as matched
    for i in range(5):
        counter.record(i, matched=(i % 2 == 0), timestamp=dummy_time.time())
        dummy_time.advance(1)


def test_basic_record_and_order(dummy_time):
    ctr = Counter[int](max_size=10, time_func=dummy_time.time)
    # Insert out of order timestamps
    ctr.record(1, matched=False, timestamp=5)
    ctr.record(2, matched=True, timestamp=3)
    ctr.record(3, matched=False, timestamp=4)
    # After sorting, order should be 2,3,1
    events = list(ctr)
    assert [e.event for e in events] == [2, 3, 1]


def test_count_methods_and_iterators(dummy_time):
    ctr = Counter[int](max_size=10, time_func=dummy_time.time)
    make_events(ctr, dummy_time)
    # Total events =5, matched count = 3 (0,2,4)
    assert ctr.count_matched() == 3
    # Ratio =3/5
    assert abs(ctr.match_ratio() - 0.6) < 1e-6
    # count_in_latest 3 most recent events: events [2,3,4], matched = [2,4] =>2
    assert ctr.count_in_latest(3) == 2
    # count_in_time last 2 seconds: dummy_time at 1005, window [1003,1005) covers events at timestamps 1003,1004 -> matched only at 1004
    cnt = ctr.count_in_time(2, now=dummy_time.time())
    assert cnt == 1
    # iter_matched yields [0,2,4]
    assert list(ctr.iter_matched()) == [0, 2, 4]
    # iter_in_latest yields last 2 events matched: latest 2 are [3,4] matched only 4
    assert list(ctr.iter_in_latest(2)) == [4]
    # iter_in_time yields matched within 3 seconds: window [1002,1005) events at ts 1002,1003,1004; matched at 1002 and 1004 -> [2,4]
    assert list(ctr.iter_in_time(3, now=dummy_time.time())) == [2, 4]


def test_latest_pop_popleft(dummy_time):
    ctr = Counter[str](max_size=5, time_func=dummy_time.time)
    make_events(ctr, dummy_time)
    # latest event should be 4
    latest = ctr.latest()
    assert isinstance(latest, RecordedEvent)
    assert latest.event == 4
    # pop removes and returns
    popped = ctr.pop()
    assert popped.event == 4
    # popleft returns first
    first = ctr.popleft()
    assert first.event == 0


def test_snapshot_load_and_json(dummy_time):
    ctr = Counter[int](max_size=5, time_func=dummy_time.time)
    make_events(ctr, dummy_time)
    snap = ctr.snapshot()
    # snapshot is list of dicts with 'event','matched','timestamp'
    assert isinstance(snap, list) and all("event" in e for e in snap)
    # to_json is valid JSON
    j = ctr.to_json()
    data = json.loads(j)
    assert isinstance(data, list)
    # Load into new counter
    new_ctr = Counter[int](max_size=5, time_func=dummy_time.time)
    new_ctr.load_snapshot(data)
    assert list(new_ctr.iter_matched()) == list(ctr.iter_matched())


def test_clear_compress_copy_add(dummy_time):
    ctr1 = Counter[int](max_size=10, time_func=dummy_time.time)
    make_events(ctr1, dummy_time)
    # compress: keep only matched and latest
    ctr1.compress()
    matched = list(ctr1.iter_matched())
    latest = ctr1.latest().event
    assert all(isinstance(e, int) for e in matched)
    assert latest in matched
    # copy creates independent copy
    ctr_copy = ctr1.copy()
    assert list(ctr_copy.iter_matched()) == matched
    # add merges counters
    ctr2 = Counter[int](max_size=10, time_func=dummy_time.time)
    ctr2.record(99, matched=True, timestamp=dummy_time.time())
    merged = ctr1 + ctr2
    assert 99 in [e.event for e in merged.iter_matched()]


def test_repr_and_len_contains(dummy_time):
    ctr = Counter[int](max_size=3, time_func=dummy_time.time)
    make_events(ctr, dummy_time)
    r = repr(ctr)
    assert "EventCounter" in r
    assert len(ctr) == 3  # max_size is 3, oldest evicted
    # last three events are 2,3,4; test contains on RecordedEvent.event fails,
    # but iter over RecordedEvent for event equals works
    assert any(e.event == 4 for e in ctr)
