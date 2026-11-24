"""Offline rank certificates for the first C135 current-wave prepin divergence."""

from critical import generation, require, wave_inputs
from current_wave import reload_observations
from oracle import logical_waves, snapshots


def rank_winner(eligible, observed):
    """A minimum of a superset is the minimum of a subset containing it.

    Each unprotected slot retains its original occupant, hotness, LRU stamp
    and physical index during this single locked reservation pass. Comparison
    therefore includes the final source tie-break by physical slot.
    """
    proofs = [(seq, winner) for seq, larger, winner in observed
              if eligible <= larger and winner in eligible]
    require(proofs and len({winner for _, winner in proofs}) == 1,
            "historical minima do not identify this victim")
    return proofs[0]


def first_wave(all_rows):
    rows = [e for e in all_rows if e["call_id"] == 2]
    observed = reload_observations(rows)
    early = min((seq, wave, demand) for wave, target, seq, _, demand in observed.values()
                if wave == target)
    first, wave, recalled = early
    tile, layer, number = wave
    require(early == (2569, (0, 12, 0), 2578), "first prepin divergence changed")
    initial = snapshots(all_rows)[0][layer]
    waves = logical_waves(all_rows)[0][layer]
    require(waves[0][0] == (tile, number) and waves[1][0] == (tile, number + 1),
            "unrecognized first waves")
    items, following = waves[0][1], waves[1][1]
    require(len(set(initial)) == len(initial) == 40 and None not in initial
            and -1 not in initial and len(items) >= 4, "unknown initial payload or parking")
    layer_rows = [r for r in rows if r["layer"] == layer]
    begin = next(r["seq"] for r in layer_rows if r["kind"] == "DEMAND")
    barrier = next(r["seq"] for r in layer_rows if r["kind"] == "WAIT_BEGIN")
    wait_end = next(r["seq"] for r in layer_rows if r["kind"] == "WAIT_END")
    pending = set()
    for r in all_rows[:begin]:
        if r["layer"] == layer:
            if r["kind"] == "RESERVE":
                pending.add(r["slot"])
            elif r["kind"] == "LOAD_END":
                pending.remove(r["slot"])
    require(not pending, "outstanding reservation on wave entry")
    stage = [r for r in layer_rows if begin <= r["seq"] < barrier]
    require(not any(r["kind"] in ("DEQUEUE", "LOAD_END", "VICTIM_WAIT_BEGIN") for r in stage),
            "resource not locked throughout picks")
    evictions = [r for r in stage if r["kind"] == "EVICT"]
    baseline = initial[:]
    candidate = initial[:]
    eligible = {s for s, e in enumerate(initial) if e not in following}
    relaxed = eligible - {s for s, e in enumerate(initial) if e in items}
    # Baseline emits the victim and incoming expert under the same mutex.
    # Every reserved slot is kept afterwards, including next-wave preloads.
    certificates = []
    n = 0
    for expert in items + following:
        if expert in baseline:
            slot = baseline.index(expert)
        else:
            ev = evictions[n]
            n += 1
            slot = ev["slot"]
            require(slot in eligible and (ev["expert"], ev["victim"]) ==
                    (baseline[slot], expert), "historical victim identity mismatch")
            certificates.append((ev["seq"], eligible.copy(), slot))
            baseline[slot] = expert
        eligible.discard(slot)
    require(n == len(evictions), "unmatched eviction")

    reroute = []
    for expert in items + following:
        if expert in candidate:
            slot = candidate.index(expert)
        else:
            seq, slot = rank_winner(relaxed, certificates)
            reroute.append([expert, candidate[slot], slot, seq])
            candidate[slot] = expert
        relaxed.discard(slot)
    diff = [[s, old, new] for s, (old, new) in enumerate(zip(baseline, candidate, strict=True))
            if old != new]
    require(diff == [[0, 79, 58], [6, 58, 44], [13, 44, 79]]
            and sorted(baseline) == sorted(candidate), "wave endpoint differs")
    require(all(old in items and new in items for _, old, new in diff),
            "displaced slot would retain an unrefreshed LRU stamp")
    require(len(reroute) == n - 1, "one-shot load count differs")
    # One unique RESERVE per accepted generation at this stage. Match the
    # barrier to all nonresident consumer generations, not to the preload.
    jobs = wave_inputs(rows)[1][wave]
    ends = {generation(e): e["seq"] for e in layer_rows if e["kind"] == "LOAD_END"}
    last = max((ends[k], k) for _, k in jobs)
    require(all(barrier < ends[k] < wait_end for _, k in jobs)
            and last == (2677, (12, 58, 6, 4)), "last required publication changed")
    future = {}
    for expert in (14, 111, 28):
        next_use = next((e for e in all_rows if wait_end < e["seq"] and e["call_id"] <= 3
                         and e["layer"] == layer and e["kind"] == "DEMAND"
                         and e["expert"] == expert), None)
        future[expert] = None if next_use is None else [next_use["call_id"], next_use["seq"]]
    return {
        "evidence": "TRACE_DERIVED_FIRST_DIVERGENCE_WITH_OBSERVED_R0_SUFFIX",
        "wave_tile_layer_wave": wave, "eviction_seq": first, "repeat_demand_seq": recalled,
        "baseline_reservations": n, "prepin_reservations": len(reroute),
        "prepin_admissions_expert_victim_slot_rank_witness_seq": reroute,
        "physical_change_slot_baseline_prepin": diff,
        "use_counter_at_wave_exit_delta": len(reroute) - n,
        "last_dependency_generation": list(last[1]), "last_dependency_commit_block": last[0],
        "wait_begin_end_seq": [barrier, wait_end],
        "next_baseline_demand_through_first_decode_call_seq": future,
    }


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    from critical import EXPECTED_SHA256, sha, trace_rows, validate
    from output import publish

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    args = parser.parse_args()

    def evaluate():
        require(sha(args.trace) == EXPECTED_SHA256, "unexpected C135 trace")
        validate(args.trace)
        return {"trace_sha256": EXPECTED_SHA256, **first_wave(trace_rows(args.trace)[1])}

    publish(args.new_output_dir, evaluate)
