from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from statistics import mean

from tesy.native_trace import NativeTopKRecord, NativeTraceError


@dataclass(frozen=True)
class SlotCacheResult:
    slots: int
    accesses: int
    loads: int
    hits: int
    evictions: int


def _decode_access_sequence(
    records: list[NativeTopKRecord],
    min_graph_seq: int = 0,
) -> list[tuple[int, int]]:
    if isinstance(min_graph_seq, bool) or min_graph_seq < 0:
        raise ValueError("min_graph_seq must be a non-negative integer")

    sequence: list[tuple[int, int]] = []
    for record in records:
        if record.graph_seq < min_graph_seq or record.n_tokens != 1:
            continue
        for expert in record.experts[0]:
            sequence.append((record.layer, expert))

    if not sequence:
        raise NativeTraceError(
            "no one-token graph expert accesses remain after filtering"
        )
    return sequence


def simulate_slot_lru(
    accesses: list[tuple[int, int]],
    slots: int,
) -> SlotCacheResult:
    if isinstance(slots, bool) or not isinstance(slots, int) or slots < 0:
        raise ValueError("slots must be a non-negative integer")

    cache: OrderedDict[tuple[int, int], None] = OrderedDict()
    loads = 0
    hits = 0
    evictions = 0

    for key in accesses:
        if key in cache:
            cache.move_to_end(key)
            hits += 1
            continue

        loads += 1
        if slots == 0:
            continue
        if len(cache) >= slots:
            cache.popitem(last=False)
            evictions += 1
        cache[key] = None

    return SlotCacheResult(
        slots=slots,
        accesses=len(accesses),
        loads=loads,
        hits=hits,
        evictions=evictions,
    )


def native_cache_headroom(
    records: list[NativeTopKRecord],
    slots: list[int],
    min_graph_seq: int = 0,
) -> dict[str, object]:
    if not slots:
        raise ValueError("at least one slot capacity is required")
    if len(set(slots)) != len(slots):
        raise ValueError("slot capacities must be unique")

    accesses = _decode_access_sequence(records, min_graph_seq=min_graph_seq)
    unique = len(set(accesses))
    no_cache_loads = len(accesses)

    results = [
        simulate_slot_lru(accesses, capacity)
        for capacity in sorted(slots)
    ]

    return {
        "schema": "tesy.native_cache_headroom.v1",
        "classification": "TRACE_DERIVED_COUNT_SPACE",
        "min_graph_seq": min_graph_seq,
        "one_token_expert_accesses": no_cache_loads,
        "unique_layer_experts": unique,
        "infinite_cache_compulsory_load_lower_bound": unique,
        "infinite_cache_max_load_reduction_fraction": (
            (no_cache_loads - unique) / no_cache_loads
        ),
        "lru": [
            {
                "slots": result.slots,
                "loads": result.loads,
                "hits": result.hits,
                "evictions": result.evictions,
                "hit_rate": result.hits / result.accesses,
                "load_reduction_fraction_vs_no_cache": (
                    (result.accesses - result.loads) / result.accesses
                ),
            }
            for result in results
        ],
        "mean_lru_loads": mean(result.loads for result in results),
        "claim_boundary": (
            "Count-space routing headroom only. Expert objects are treated as "
            "equal-sized slots. This is not a byte, latency, I/O or optimal-cache claim."
        ),
    }
