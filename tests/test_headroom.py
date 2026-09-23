from __future__ import annotations

from tesy.headroom import (
    native_cache_headroom,
    simulate_slot_belady,
    simulate_slot_lru,
)
from tesy.native_trace import NativeTopKRecord


def _record(graph: int, layer: int, experts: tuple[int, ...]) -> NativeTopKRecord:
    return NativeTopKRecord(graph_seq=graph, layer=layer, experts=(experts,))


def test_lru_and_belady_equal_when_cache_holds_working_set():
    accesses = [(0, 0), (0, 1), (0, 0), (0, 1)]
    lru = simulate_slot_lru(accesses, 2)
    opt = simulate_slot_belady(accesses, 2)
    assert lru.loads == 2
    assert opt.loads == 2


def test_belady_beats_lru_on_known_sequence():
    accesses = [
        (0, 1),
        (0, 2),
        (0, 3),
        (0, 1),
        (0, 2),
        (0, 4),
        (0, 1),
        (0, 2),
        (0, 3),
        (0, 4),
    ]
    lru = simulate_slot_lru(accesses, 3)
    opt = simulate_slot_belady(accesses, 3)
    assert opt.loads < lru.loads


def test_zero_slots_means_every_access_loads():
    accesses = [(0, 1), (0, 1), (0, 2)]
    assert simulate_slot_lru(accesses, 0).loads == 3
    assert simulate_slot_belady(accesses, 0).loads == 3


def test_native_headroom_reports_offline_oracle():
    records = [
        _record(0, 0, (0, 1)),
        _record(1, 0, (0, 2)),
        _record(2, 0, (0, 1)),
    ]
    result = native_cache_headroom(records, [0, 1, 2])
    assert result["schema"] == "tesy.native_cache_headroom.v2"
    assert len(result["lru"]) == 3
    assert len(result["belady_offline_oracle"]) == 3
    for lru, oracle in zip(
        result["lru"], result["belady_offline_oracle"], strict=True
    ):
        assert oracle["loads"] <= lru["loads"]
