"""Conditional ceilings on C135 call-2 WAIT exposure, with immutable wave geometry.

Run from any directory in a Tesy checkout. LOAD_END times precede publication.
The sequence position, rather than the sampling time, orders the publications.
"""

import argparse
import json
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from c122_trace_validate import validate  # noqa: E402
from c123_analyze_trace import sha, trace_rows  # noqa: E402

EXPECTED_SHA256 = "91610b12291d5a42a12bba09f5d4ff188d25ee0001ab89e894bdd508005e82fb"
TILE_WIDTHS = (32, 32, 32, 32, 20)
# These stamps are taken under the common manager mutex in the trace backend.
LOCKED = {
    "CALL_BEGIN", "CALL_END", "DEMAND", "PRELOAD", "RESERVE", "EVICT", "ENQUEUE",
    "DEQUEUE", "WAIT_BEGIN", "WAIT_END", "MUTEX_WAIT_END",
    "VICTIM_WAIT_BEGIN", "VICTIM_WAIT_END",
}


def require(test, reason):
    if not test:
        raise ValueError(reason)


def generation(e):
    return e["layer"], e["expert"], e["slot"], e["generation"]


def commit_bounds(rows):
    """Bracket the instant of assigning RESIDENT in a successful trace.

    The worker flushes its LOAD_BEGIN..LOAD_END block, then assigns RESIDENT
    before unlocking. LOAD_END is sampled before reacquiring the mutex. Every
    earlier sample has happened by the time this block is flushed. Every later
    in-lock sample follows this block. Instrument timestamps are in whole us.
    """
    upper = {}
    next_locked = None
    for row in reversed(rows):
        if row["kind"] in LOCKED:
            next_locked = row["mono_us"]
        if row["kind"] == "LOAD_END":
            require(next_locked is not None, "no following mutex stamp")
            upper[generation(row)] = next_locked
    lower = 0
    finished = {}
    for row in rows:
        lower = max(lower, row["mono_us"])
        if row["kind"] == "LOAD_END":
            key = generation(row)
            require(key not in finished and lower <= upper[key], "unbracketed publication")
            finished[key] = (row["seq"], lower, upper[key])
    return finished


def wave_inputs(rows):
    """Join nonresident demands to the original slot generation via the promotion enqueue."""
    enqueue_lists = defaultdict(list)
    enqueue_key = {}
    first_enqueue = {}
    service = {}
    for row in rows:
        key = generation(row)
        kind = row["kind"]
        if kind == "ENQUEUE":
            enqueue_lists[key[:2]].append(row["seq"])
            enqueue_key[row["seq"]] = key
            first_enqueue.setdefault(key, (row["seq"], row["mono_us"]))
        elif kind == "LOAD_BEGIN":
            service[key] = row["mono_us"]
        elif kind == "LOAD_END":
            service[key] = row["mono_us"] - service[key]

    demands = defaultdict(list)
    waits = {}
    last_seen = {}
    candidates = set()
    first_demand = {}
    load_scope = {}
    tile, previous_layer = -1, 36
    for row in rows:
        kind, layer, expert, wave = (row[k] for k in ("kind", "layer", "expert", "wave"))
        if kind == "DEMAND":
            if layer < previous_layer:
                tile += 1
                require(layer == 0 and tile < len(TILE_WIDTHS)
                        and row["n_tokens"] == TILE_WIDTHS[tile], "call-2 tile boundary")
            previous_layer = layer
            first_demand.setdefault((tile, layer), row["mono_us"])
            if row["state"] == 2:
                last_seen[layer, expert] = tile
            else:
                matches = enqueue_lists[layer, expert]
                pos = bisect_right(matches, row["seq"])
                require(pos < len(matches), "missing enqueue after nonresident demand")
                seq = matches[pos]
                key = enqueue_key[seq]
                require(row["slot"] in (-1, key[2]), "promoted slot identity differs")
                demands[tile, layer, wave].append((seq, key))
        elif kind == "ENQUEUE":
            require(layer == previous_layer, "enqueue outside active demand layer")
            load_scope.setdefault(generation(row), (tile, layer))
        elif kind == "LOAD_BEGIN":
            key = generation(row)
            require(load_scope[key] == (tile, previous_layer), "load spans layer scopes")
            prior = last_seen.get(key[:2])
            if prior is not None and prior < tile:
                candidates.add(key)
            last_seen[key[:2]] = tile
        elif kind in ("WAIT_BEGIN", "WAIT_END"):
            waits.setdefault((tile, layer, wave), []).append(row)
    require(tile == 4 and set(waits) == set(demands), "unreconciled demand/wait")
    require(set(service) == set(load_scope), "unaccepted generation in scope")
    return candidates, demands, waits, service, first_enqueue, first_demand, load_scope


def direct_window(start, end, ordered, removed, published):
    """Local maximum direct relief of this barrier under frozen co-dependencies.

    Relative to WAIT_BEGIN, fix all retained publication times and preserve
    the wake tail if any dependency remains. Credit the full WAIT if all
    dependencies disappear. Bounds allow one us for timestamp quantization
    on either end of a duration. Claim only intervals in the traced clock.
    """
    last = ordered[-1]
    if last not in removed:
        return 0, 0
    retained = [k for k in ordered if k not in removed]
    if not retained:
        return max(0, end - start - 1), end - start + 1
    prev = retained[-1]
    _, prev_lo, prev_hi = published[prev]
    _, last_lo, last_hi = published[last]
    return max(0, last_lo - prev_hi - 1), min(end - start, last_hi - prev_lo) + 1


def selection_keys(rows, selected):
    # Accept LOAD_BEGIN sequence numbers, (layer, slot, generation), or full
    # (layer, expert, slot, generation) identities, all from this call only.
    lookup = {}
    for e in rows:
        if e["kind"] == "LOAD_BEGIN":
            key = generation(e)
            for identity in (e["seq"], (key[0], key[2], key[3]), key):
                require(identity not in lookup, "non-unique load identity")
                lookup[identity] = key
    result = set()
    for item in selected:
        identity = tuple(item) if isinstance(item, list) else item
        require(identity in lookup, "unknown selected load identity")
        key = lookup[identity]
        require(key not in result, "duplicate selected generation")
        result.add(key)
    return result


def summarize(rows, selected=None, *, eligibility=None):
    rows = [row for row in rows if row["call_id"] == 2]
    require(rows[0]["kind"] == "CALL_BEGIN" and rows[-1]["kind"] == "CALL_END"
            and not any(r["kind"] == "VICTIM_WAIT_BEGIN" for r in rows),
            "call scope or victim stalls require a different model")
    published = commit_bounds(rows)
    inputs = wave_inputs(rows)
    candidates, demands, waits, service, first_enqueue, first_demand, load_scope = inputs
    require(Counter("CPU" if k[0] < 25 else "CUDA0" for k in candidates)
            == {"CPU": 102, "CUDA0": 82}, "cross-tile eligibility disagrees with C135")
    # The default universe is the frozen cross-tile gate. Another study may
    # supply its independently reconstructed identities from the same journal.
    if eligibility is not None:
        candidates = selection_keys(rows, eligibility)
    removed = candidates if selected is None else selection_keys(rows, selected)
    require(removed <= candidates, "credit outside selected admissible universe")
    counts = Counter()
    spans = []
    witness = None
    # LOAD_END records precede the RESIDENT assignment in the same mutex
    # section. A later locked DEMAND(state=2) can witness consumption of a
    # generation even if that preload finished before the demand was issued.
    resident, ready_witness = {}, set()
    for row in rows:
        where = row["layer"], row["slot"]
        if row["kind"] in ("EVICT", "RESERVE"):
            resident.pop(where, None)
        elif row["kind"] == "LOAD_END":
            resident[where] = generation(row)
        elif row["kind"] == "DEMAND" and row["state"] == 2 and where in resident:
            key = resident[where]
            require(key[1] == row["expert"], "slot identity at resident demand")
            ready_witness.add(key)
    removed_in_waits = set()
    loose_by_scope = Counter()
    relevant_scopes = {load_scope[key] for key in removed}
    all_wait_us = 0
    for wave, markers in waits.items():
        require([m["kind"] for m in markers] == ["WAIT_BEGIN", "WAIT_END"], "wait lifecycle")
        a, b = markers
        start, end = a["mono_us"], b["mono_us"]
        spans.append((start, end))
        work = demands[wave]
        require(all(seq < a["seq"] < published[k][0] < b["seq"] for seq, k in work),
                "demand and committed generation do not enclose exact wait")
        ordered = sorted((k for _, k in work), key=lambda k: published[k][0])
        require(len(ordered) == len(set(ordered)), "duplicate generation at one barrier")
        eligible = set(ordered) & removed
        last = ordered[-1]
        counts["wait_us"] += end - start
        counts["barriers"] += 1
        removed_in_waits.update(eligible)
        if wave[:2] in relevant_scopes:
            all_wait_us += end - start
        if eligible:
            counts["barriers_with_candidates"] += 1
            counts["whole_wait_us_at_barriers_with_candidates"] += end - start
            if last in eligible:
                counts["last_dependency_is_candidate"] += 1
            elif witness is None:
                earlier = next(k for k in ordered if k in eligible)
                witness = {
                    "tile_zero_based_layer_wave": wave,
                    "wait_begin_end_seq": [a["seq"], b["seq"]],
                    "wait_us": end - start,
                    "candidate_layer_expert_slot_generation": earlier,
                    "candidate_commit_block_seq": published[earlier][0],
                    "last_retained_layer_expert_slot_generation": last,
                    "last_retained_commit_block_seq": published[last][0],
                }
        low, high = direct_window(start, end, ordered, removed, published)
        counts["direct_saving_lower_us"] += low
        counts["direct_saving_upper_us"] += high

        # Relax worker assignment and arbitration while retaining wave releases,
        # each remaining job's own observed span, and four workers. For each
        # retained generation, its original enqueue relative to this wait gives
        # an earliest release ONLY if it was first enqueued by this wave. A
        # previously preloaded job may be fully complete in the relaxed case.
        required = [(first_enqueue[k][1], service[k]) for seq, k in work
                    if k not in removed and seq == first_enqueue[k][0]]
        if required:
            # Lower bounds for the final required completion, measured from WAIT_BEGIN.
            single = max(t + duration - start for t, duration in required)
            capacity = (sum(d for _, d in required) // 4
                        + min(t for t, _ in required) - start)
            unavoidable = max(0, single - 2, capacity - 2)
        else:
            unavoidable = 0
        require(unavoidable <= end - start + 1, "inconsistent retained service durations")
        loose_by_scope[wave[:2]] += end - start + 1 - unavoidable
    require(all(b <= c for (_, b), (c, _) in zip(sorted(spans), sorted(spans)[1:], strict=False)),
            "WAIT clocks overlap")
    counts["removed_pending_at_a_demand_barrier"] = len(removed_in_waits)
    require(removed - removed_in_waits <= ready_witness, "candidate lacks consuming demand")
    counts["removed_ready_at_demand"] = len(removed - removed_in_waits)
    counts["affected_tile_layer_scopes"] = len(relevant_scopes)
    counts["wait_us_in_affected_scopes"] = all_wait_us

    # Start a scope at its first demand and end at the next scope's first
    # demand (or call end). Retained reads all enter and finish within their
    # original scope. Four workers cannot deliver them in less than their
    # summed occupied service duration / 4. Using the full scope elapsed
    # time includes compute and gives a conservative bound. No redistribution
    # of work across these intervals is part of this fixed-arrival model.
    scopes = list(first_demand)
    starts = list(first_demand.values())
    ends = starts[1:] + [rows[-1]["mono_us"]]
    retained_work = Counter()
    for key, duration in service.items():
        if key not in removed:
            retained_work[load_scope[key]] += max(0, duration - 1)
    flexible_bound = 0
    for scope, start, end in zip(scopes, starts, ends, strict=True):
        if scope in relevant_scopes:
            scoped_cap = end - start + 1 - retained_work[scope] // 4
            require(scoped_cap >= 0, "retained service exceeds available capacity")
            flexible_bound += min(scoped_cap, loose_by_scope[scope])
    counts["fixed_wave_release_flexible_dispatch_saving_upper_us"] = flexible_bound
    return {
        "call2_us": rows[-1]["mono_us"] - rows[0]["mono_us"],
        "removed_generations": len(removed),
        "candidate_generations": len(candidates),
        "conditional_projection": dict(counts),
        "last_dependency_retained_witness": witness,
    }


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--trace", type=Path, required=True)
    cli.add_argument("--selected", type=Path, help="JSON array of call-2 LOAD_BEGIN seq or keys")
    args = cli.parse_args()
    require(sha(args.trace) == EXPECTED_SHA256, "C135 SHA-256 mismatch")
    validate(args.trace)
    metadata, rows = trace_rows(args.trace)
    selected = json.loads(args.selected.read_text()) if args.selected else None
    print(json.dumps(summarize(rows, selected), indent=2, allow_nan=False))
