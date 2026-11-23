from __future__ import annotations

from collections import OrderedDict, defaultdict, deque
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


def _validate_slots(slots: int) -> None:
    if isinstance(slots, bool) or not isinstance(slots, int) or slots < 0:
        raise ValueError("slots must be a non-negative integer")


def simulate_slot_lru(
    accesses: list[tuple[int, int]],
    slots: int,
) -> SlotCacheResult:
    _validate_slots(slots)

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


def simulate_slot_belady(
    accesses: list[tuple[int, int]],
    slots: int,
) -> SlotCacheResult:
    """Offline optimal cache for equal-sized expert slots.

    Belady's policy evicts the resident object whose next use is farthest in
    the future (or never occurs again). It is deliberately non-causal and is
    used only as a headroom lower bound on loads.
    """
    _validate_slots(slots)

    future: dict[tuple[int, int], deque[int]] = defaultdict(deque)
    for index, key in enumerate(accesses):
        future[key].append(index)

    cache: set[tuple[int, int]] = set()
    loads = 0
    hits = 0
    evictions = 0

    for index, key in enumerate(accesses):
        queue = future[key]
        if not queue or queue[0] != index:
            raise RuntimeError("internal future-use index corruption")
        queue.popleft()

        if key in cache:
            hits += 1
            continue

        loads += 1
        if slots == 0:
            continue

        if len(cache) >= slots:
            def next_use(candidate: tuple[int, int]) -> float:
                candidate_future = future[candidate]
                return float(candidate_future[0]) if candidate_future else float("inf")

            victim = max(cache, key=next_use)
            cache.remove(victim)
            evictions += 1

        cache.add(key)

    return SlotCacheResult(
        slots=slots,
        accesses=len(accesses),
        loads=loads,
        hits=hits,
        evictions=evictions,
    )


def _serialize_result(result: SlotCacheResult) -> dict[str, object]:
    accesses = result.accesses
    return {
        "slots": result.slots,
        "loads": result.loads,
        "hits": result.hits,
        "evictions": result.evictions,
        "hit_rate": result.hits / accesses,
        "load_reduction_fraction_vs_no_cache": (
            (accesses - result.loads) / accesses
        ),
    }


def native_cache_headroom(
    records: list[NativeTopKRecord],
    slots: list[int],
    min_graph_seq: int = 0,
) -> dict[str, object]:
    if not slots:
        raise ValueError("at least one slot capacity is required")
    if len(set(slots)) != len(slots):
        raise ValueError("slot capacities must be unique")
    for capacity in slots:
        _validate_slots(capacity)

    accesses = _decode_access_sequence(records, min_graph_seq=min_graph_seq)
    unique = len(set(accesses))
    no_cache_loads = len(accesses)

    capacities = sorted(slots)
    lru_results = [simulate_slot_lru(accesses, capacity) for capacity in capacities]
    oracle_results = [
        simulate_slot_belady(accesses, capacity) for capacity in capacities
    ]

    for lru, oracle in zip(lru_results, oracle_results, strict=True):
        if oracle.loads > lru.loads:
            raise RuntimeError("offline oracle cannot load more objects than LRU")

    return {
        "schema": "tesy.native_cache_headroom.v2",
        "classification": "TRACE_DERIVED_COUNT_SPACE",
        "min_graph_seq": min_graph_seq,
        "one_token_expert_accesses": no_cache_loads,
        "unique_layer_experts": unique,
        "infinite_cache_compulsory_load_lower_bound": unique,
        "infinite_cache_max_load_reduction_fraction": (
            (no_cache_loads - unique) / no_cache_loads
        ),
        "lru": [_serialize_result(result) for result in lru_results],
        "belady_offline_oracle": [
            _serialize_result(result) for result in oracle_results
        ],
        "mean_lru_loads": mean(result.loads for result in lru_results),
        "mean_belady_loads": mean(result.loads for result in oracle_results),
        "claim_boundary": (
            "Count-space routing headroom only. Expert objects are treated as "
            "equal-sized slots. Belady uses future accesses and is an offline "
            "non-causal lower bound, not an implementable policy. This is not a "
            "byte, latency, I/O or production-cache claim."
        ),
    }
