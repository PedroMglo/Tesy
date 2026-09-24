from __future__ import annotations

import pytest

from tesy.headroom import (
    native_cache_headroom,
    simulate_slot_belady,
    simulate_slot_lru,
)
from tesy.native_trace import NativeTopKRecord, NativeTraceError


def _record(graph, layer, experts, phase="decode"):
    return NativeTopKRecord(
        graph_seq=graph,
        layer=layer,
        experts=(experts,),
        phase=phase,
    )


def test_lru_and_belady_equal_when_cache_holds_working_set():
    accesses = [(0, 0), (0, 1), (0, 0), (0, 1)]
    assert simulate_slot_lru(accesses, 2).loads == 2
    assert simulate_slot_belady(accesses, 2).loads == 2


def test_belady_beats_lru_on_known_sequence():
    accesses = [
        (0, 1), (0, 2), (0, 3), (0, 1), (0, 2),
        (0, 4), (0, 1), (0, 2), (0, 3), (0, 4),
    ]
    assert simulate_slot_belady(accesses, 3).loads < simulate_slot_lru(accesses, 3).loads


def test_zero_slots_means_every_access_loads():
    accesses = [(0, 1), (0, 1), (0, 2)]
    assert simulate_slot_lru(accesses, 0).loads == 3
    assert simulate_slot_belady(accesses, 0).loads == 3


def test_native_headroom_excludes_one_token_prefill():
    records = [
        _record(0, 0, (9,), phase="prefill"),
        _record(1, 0, (0, 1)),
        _record(2, 0, (0, 2)),
        _record(3, 0, (0, 1)),
    ]
    result = native_cache_headroom(records, [0, 1, 2])
    assert result["one_token_expert_accesses"] == 6


def test_native_headroom_rejects_legacy_phase_unknown():
    with pytest.raises(NativeTraceError):
        native_cache_headroom([_record(0, 0, (0,), phase=None)], [1])
