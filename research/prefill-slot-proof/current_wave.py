"""Direct relief of prematurely evicting residents of an already-authoritative wave."""

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path

from critical import (
    EXPECTED_SHA256,
    generation,
    require,
    sha,
    summarize,
    trace_rows,
    validate,
    wave_inputs,
)
from critical_intervals import interval_report
from output import publish


def reload_observations(rows):
    """Link an absent expert's refill to its preceding eviction and next consumer."""
    tile, last_layer, current = -1, 36, None
    demands = defaultdict(list)
    routes = defaultdict(list)
    writes = {}
    evicted = {}
    pairs = {}
    by_seq = {}
    for row in rows:
        kind, seq, layer, expert, slot = (
            row[k] for k in ("kind", "seq", "layer", "expert", "slot")
        )
        logical, place = (layer, expert), (layer, slot)
        if kind == "DEMAND":
            if layer < last_layer:
                require(layer == 0, "unknown numerical tile boundary")
                tile += 1
            last_layer = layer
            current = (tile, layer, row["wave"])
            demands[logical].append(seq)
            routes[current].append(expert)
            by_seq[seq] = (current, row)
        elif kind == "EVICT":
            require(
                current is not None and current[1] == layer and row["state"] == 2,
                "victim outside a known wave or not READY",
            )
            require(logical not in evicted, "expert evicted twice without service")
            evicted[logical] = (seq, current, slot, writes.get(place) == current)
        elif kind in ("RESERVE", "LOAD_END"):
            writes[place] = current
        elif kind == "LOAD_BEGIN" and logical in evicted:
            key = generation(row)
            require(key not in pairs, "generation refilled twice")
            pairs[key] = (current, evicted.pop(logical))
    ret = {}
    for key, (loaded, (eviction, origin, slot, written_here)) in pairs.items():
        seqs = demands[key[:2]]
        pos = bisect_right(seqs, eviction)
        require(pos < len(seqs), "refilled expert has no consumer after eviction")
        consumer, demand = by_seq[seqs[pos]]
        require(consumer[:2] == loaded[:2], "refill and consumer belong to different tiles")
        if origin == consumer:
            # The source victim was present before admission started. A victim
            # later installed by this wave would not qualify for pre-marking.
            here = routes[origin]
            require(
                origin[2] == 0 and 4 <= len(here) <= 18 and len(set(here)) == len(here),
                "source wave may borrow parking or has repeated logical demands",
            )
            after = (origin[0], origin[1], origin[2] + 1)
            require(
                key[1] not in routes.get(after, ()), "victim belonged to already-pinned next wave"
            )
            require(not written_here, "resident was installed during current wave")
            require(
                consumer[2] >= 0 and demand["state"] == 0 and demand["slot"] == -1,
                "consumer of same-wave victim did not demand an absent expert",
            )
        ret[key] = (origin, consumer, eviction, slot, seqs[pos])
    return ret


def diagnose(all_rows):
    rows = [row for row in all_rows if row["call_id"] == 2]
    cross, demand_work, *_ = wave_inputs(rows)
    observations = reload_observations(rows)
    require(cross <= observations.keys(), "cross-tile readmission has no source eviction")
    same, partition, tiers = set(), Counter(), Counter()
    transitions = Counter()
    for key, (origin, consumer, _, _, demand_seq) in observations.items():
        if origin == consumer:
            work = [accept for accept, job in demand_work.get(consumer, ()) if job == key]
            require(
                len(work) == 1 and work[0] > demand_seq, "no matching accepted job at this barrier"
            )
            same.add(key)
            tiers["CPU" if key[0] < 25 else "CUDA0"] += 1
        if key not in cross:
            continue
        if origin[:2] != consumer[:2]:
            partition["source_in_earlier_tile"] += 1
        elif origin == consumer:
            partition["source_in_consumer_wave"] += 1
        else:
            partition["source_in_earlier_wave_of_consumer_tile"] += 1
        if origin[:2] == consumer[:2]:
            transitions[f"{origin[2]}->{consumer[2]}"] += 1
    require(
        len(cross) == 184 and len(same) == 79 and len(cross & same) == 63,
        "C135 eligibility fingerprint changed",
    )
    times = summarize(rows, eligibility=same)
    intervals = interval_report(rows, eligibility=same)
    return {
        "evidence": "TRACE_DERIVED_C135_CONDITIONAL_FIXED_OTHER_WORK",
        "trace_sha256": EXPECTED_SHA256,
        "call2_original_same_wave_reload_count_by_tier": dict(tiers),
        "same_wave_overlapping_the_184": len(same & cross),
        "same_wave_outside_the_184": len(same - cross),
        "partition_of_184_by_victim_eviction": dict(partition),
        "same_tile_transitions_among_the_184": dict(transitions),
        "unchanged_other_load_stream": times,
        "four_worker_bounds_us": intervals,
    }


def evaluate(trace):
    require(sha(trace) == EXPECTED_SHA256, "unexpected C135 trace")
    validate(trace)
    return diagnose(trace_rows(trace)[1])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    publish(args.new_output_dir, lambda: evaluate(args.trace))
