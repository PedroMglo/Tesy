from __future__ import annotations

import pytest

from tesy.headroom import native_cache_headroom, simulate_slot_lru
from tesy.native_trace import NativeTopKRecord


def _record(
    graph: int,
    layer: int,
    experts: tuple[int, ...],
) -> NativeTopKRecord:
    return NativeTopKRecord(
        graph_seq=graph,
        layer=layer,
        experts=(experts,),
    )


def test_slot_lru_reuses_hot_expert() -> None:
    accesses = [(0, 1), (0, 2), (0, 1)]
    result = simulate_slot_lru(accesses, slots=2)
    assert result.loads == 2
    assert result.hits == 1
    assert result.evictions == 0


def test_zero_slot_cache_loads_every_access() -> None:
    accesses = [(0, 1), (0, 1)]
    result = simulate_slot_lru(accesses, slots=0)
    assert result.loads == 2
    assert result.hits == 0


def test_headroom_reports_infinite_cache_lower_bound() -> None:
    records = [
        _record(0, 0, (1, 2)),
        _record(1, 0, (1, 3)),
    ]
    result = native_cache_headroom(records, [0, 2, 3])
    assert result["one_token_expert_accesses"] == 4
    assert result["unique_layer_experts"] == 3
    assert result["infinite_cache_compulsory_load_lower_bound"] == 3
    assert result["infinite_cache_max_load_reduction_fraction"] == 0.25


def test_headroom_can_skip_initial_graphs() -> None:
    records = [
        _record(0, 0, (9,)),
        _record(1, 0, (1,)),
        _record(2, 0, (1,)),
    ]
    result = native_cache_headroom(records, [1], min_graph_seq=1)
    assert result["one_token_expert_accesses"] == 2
    assert result["unique_layer_experts"] == 1


@pytest.mark.parametrize("bad", [-1, True, 1.5])
def test_slot_capacity_is_strict(bad) -> None:
    with pytest.raises(ValueError):
        simulate_slot_lru([(0, 1)], bad)
