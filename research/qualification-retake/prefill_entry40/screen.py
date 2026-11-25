"""Offline whole-wave payload floor for the C135 cache already present at call 5."""

import argparse
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from prefill_oracle40 import screen as free  # noqa: E402

require = free.require
FREE_SHA = "bb15c34096e40ae7c12788ad274651eb40454cf5783f30bb83f26f66075d062f"
ORACLE_SHA = "eeeeb70d51529aab0fbb1476e2edaebfb5f81827bb553fedaa66e47987ffe59b"
CUTS = (("CALL_BEGIN", 1), ("CALL_END", 1), ("CALL_BEGIN", 2), ("CALL_END", 2))


def resident(slots):
    ids = [v for v in slots if v is not None and v >= 0]
    require(len(set(ids)) == len(ids), "duplicate physical resident")
    return set(ids)


def reconstruct(rows, n_layers=36, capacity=40):
    """Bind identities to slot versions. The sequence is mutex order, not READ time."""
    version = Counter()
    labels, replacement, cut_versions, gen_base = {}, {}, {}, {}

    def bind(slot, expert):
        key = (*slot, version[slot])
        require(labels.setdefault(key, expert) == expert, "conflicting witnesses in slot version")

    for r in rows:
        kind, call = r["kind"], r["call_id"]
        if (kind, call) in CUTS:
            require(not replacement and (kind, call) not in cut_versions, "unfinished cut")
            cut_versions[kind, call] = version.copy()
        if kind not in ("DEMAND", "EVICT", "RESERVE", "ENQUEUE", "LOAD_BEGIN", "LOAD_END"):
            continue
        layer, index, e = r["layer"], r["slot"], r["expert"]
        require(0 <= layer < n_layers and 0 <= e < 128, "event identity")
        if kind == "DEMAND" and r["state"] == 0:
            require(index == -1, "absent demand owns slot")
            continue
        require(0 <= index < capacity, "physical slot")
        slot = (layer, index)
        if kind == "EVICT":
            require(r["state"] == 2 and slot not in replacement, "eviction order/readiness")
            require(0 <= r["victim"] < 128 and r["victim"] != e, "replacement expert")
            bind(slot, e)
            replacement[slot] = r["victim"]
        elif kind == "RESERVE":
            if slot in replacement:
                require(replacement.pop(slot) == e, "wrong replacement")
            else:
                # C122 emits EVICT for every old slot_expert >= 0 before RESERVE.
                bind(slot, -1)
            version[slot] += 1
            bind(slot, e)
        elif kind == "DEMAND":
            require(r["state"] in (1, 2) and slot not in replacement, "demand state")
            if r["state"] == 2:
                bind(slot, e)
        else:
            require(slot not in replacement and r["generation"] > 0, "physical generation")
            require(labels.get((*slot, version[slot]), e) == e, "work identity")
            base = r["generation"] - version[slot]
            require(base >= 0 and gen_base.setdefault(slot, base) == base, "generation continuity")
    require(not replacement and set(cut_versions) == set(CUTS), "incomplete slot history")
    snapshots = {}
    for cut, versions in cut_versions.items():
        pools = []
        for layer in range(n_layers):
            slots = [labels.get((layer, s, versions[layer, s])) for s in range(capacity)]
            resident(slots)
            pools.append(slots)
        snapshots[cut] = pools
    # Check the reverse index at every mutation, including reservations outside
    # the two cuts. An unobserved initial version stays a symbol throughout.
    slots = [list(pool) for pool in snapshots[CUTS[0]]]
    index = [{e: s for s, e in enumerate(pool) if e is not None and e >= 0} for pool in slots]
    for r in rows:
        kind, layer, e, s = r["kind"], r["layer"], r["expert"], r["slot"]
        if kind == "RESERVE":
            old = slots[layer][s]
            require(old is not None, "reservation lacks an old version witness")
            if old >= 0:
                require(index[layer].pop(old) == s, "wrong source of eviction")
            require(e not in index[layer], "duplicate resident after reservation")
            slots[layer][s] = e
            index[layer][e] = s
        elif kind == "DEMAND":
            if r["state"] == 0:
                require(e not in index[layer], "absent lookup refers to known resident")
            elif slots[layer][s] is not None:
                require(index[layer].get(e) == s, "lookup refers to wrong slot")
    require(snapshots[CUTS[1]] == snapshots[CUTS[2]], "boundary between calls")
    return snapshots


def optimum(slots, groups):
    """Only unknown slots receive an initial grant. Known empties stay empty."""
    known = resident(slots)
    first_use = {}
    for i, group in enumerate(groups):
        for e in group:
            first_use.setdefault(e, i)
    candidates = sorted(first_use.keys() - known, key=lambda e: (first_use[e], e))
    grants = candidates[: slots.count(None)]
    initial = known.union(grants)
    # Exchange a later optional initial ID for an earlier one. Until the first use
    # of the earlier ID, copy all evictions. If it survives, its hit pays for the
    # possible later miss of the displaced ID, even when both are pinned together.
    loads = free.cache_bound.minimum(groups, len(slots), initial=initial)
    without_grants = free.cache_bound.minimum(groups, len(slots), initial=known)
    distinct_floor = len(first_use.keys() - initial)
    require(distinct_floor <= loads <= without_grants <= loads + len(grants), "initial grants")
    return {
        "known_residents": len(known),
        "known_empty": slots.count(-1),
        "unknown_slots": slots.count(None),
        "known_demanded": len(known & first_use.keys()),
        "known_outside_demand": len(known - first_use.keys()),
        "free_unknown_ids_granted": len(grants),
        "maximum_initial_useful": len(initial & first_use.keys()),
        "distinct_floor": distinct_floor,
        "wave_floor": loads,
        "misses_if_unknowns_unhelpful": without_grants,
    }


def bridge(entry, boundary, f5, rows5, f148, rows148, old_floor):
    """Bound the most useful possible change of state across the external return."""
    before, after = resident(entry), resident(boundary)
    require(len(entry) == len(boundary) and f5 <= after, "lost first-call demand at return")
    unknown_after = {s for s, e in enumerate(boundary) if e is None}
    require(
        all(
            r["slot"] not in unknown_after
            for r in rows148
            if r["kind"] in ("DEMAND", "RESERVE", "EVICT") and r["slot"] >= 0
        ),
        "unidentified slot touched in call 148",
    )
    # Such a slot cannot contain a demanded ID: no write, no eviction, and
    # the authoritative expert_slot lookup never identified it in any DEMAND.
    reference = free.cache_bound.minimum(f148, len(entry), initial=after)
    require(reference == old_floor, "independent fixed-entry PR45 floor")
    reserves = [r["expert"] for r in rows5 if r["kind"] == "RESERVE"]
    loads = [r["expert"] for r in rows5 if r["kind"] == "LOAD_END"]
    require(
        not any(r["kind"] == "PRELOAD" for r in rows5)
        and Counter(reserves) == Counter(loads)
        and len(reserves) == len(set(reserves))
        and set(reserves) <= f5,
        "first-call admission service",
    )
    # Every unknown survived unchanged; each reservation or eviction binds old version.
    require(
        all((a is None) == (b is None) for a, b in zip(entry, boundary, strict=True)),
        "first-call invisible replacement",
    )
    require(
        all(
            entry[r["slot"]] is not None for r in rows5 if r["kind"] == "DEMAND" and r["slot"] >= 0
        ),
        "first-call lookup in unidentified slot",
    )
    mandatory = f5 - before
    require(
        mandatory <= set(reserves)
        and (after - before) == mandatory
        and len(before - after) <= len(mandatory),
        "first-call resident-set transition",
    )
    # Even if R0 reloaded a future first-use victim in its single wave, only the
    # m strictly new F5 identities distinguish S_R from S0 in this direction.
    # A candidate paying m+k starts 148 with at most m retained R0 victims and
    # k new non-F5 IDs beyond S_R. Each such ID can save at most one miss.
    return {
        "mandatory_call5": len(mandatory),
        "extra_historical_call5_loads": len(reserves) - len(mandatory),
        "old_ids_removed": len(before - after),
        "pr45_call148_floor": reference,
        "bridge_floor": reference,
    }


def run(trace, backend, pr45):
    require(free.sha(Path(free.__file__)) == FREE_SHA, "whole-prefill oracle program")
    baseline = free.run(trace, backend, pr45)
    if baseline["status"] == "NOT_RUN_RAW_REQUIRED":
        return baseline
    oracle_path = pr45 / "research/prefill-slot-proof/oracle.py"
    require(free.sha(oracle_path) == ORACLE_SHA, "PR45 snapshot source")
    spec = importlib.util.spec_from_file_location("c135_pr45_oracle", oracle_path)
    oracle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oracle)
    _, rows = free.trace_rows(trace)
    cuts = reconstruct(rows)
    start, boundary = cuts[CUTS[0]], cuts[CUTS[2]]
    a, b = oracle.snapshots(rows)
    require(a == boundary and b == cuts[CUTS[3]], "PR45 slot-by-slot entry and return")
    parts = [[r for r in rows if r["call_id"] == call] for call in (1, 2)]
    waves = [
        free.demands_by_layer(parts[0], [5], final_output=False),
        free.demands_by_layer(parts[1], [32, 32, 32, 32, 20], final_output=True),
    ]
    reference = json.loads(
        (pr45 / "research/prefill-slot-proof/victim-evidence/receipt.json").read_text()
    )
    layers = []
    for i, slots in enumerate(start):
        first, second = waves[0][i], waves[1][i]
        lookups = [set(group) for group in first]
        require(len(lookups) == int(i < 35), "one first wave or pruned layer")
        observed = baseline["layers"][i]
        result = optimum(slots, first + second)
        bound = bridge(
            slots,
            boundary[i],
            set().union(*lookups),
            [r for r in parts[0] if r["layer"] == i],
            second,
            [r for r in parts[1] if r["layer"] == i],
            reference["by_layer"][i]["demand_only_loads"],
        )
        require(result["wave_floor"] >= observed["optimal_total"], "free oracle greater")
        floor = max(result["wave_floor"], bound["bridge_floor"])
        require(
            floor <= observed["historical_call5"] + observed["historical_call148"], "R0 feasible"
        )
        layers.append(
            {
                "layer": i,
                "tier": observed["tier"],
                **result,
                **bound,
                "free_start_floor": observed["optimal_total"],
                "combined_floor": floor,
            }
        )
    totals = {}
    for tier in ("CPU", "CUDA0", "all"):
        included = [row for row in layers if tier in (row["tier"], "all")]
        totals[tier] = {
            k: sum(row[k] for row in included) for k in included[0] if k not in ("layer", "tier")
        }
    budget = Fraction(baseline["time_scenario"]["budget_s_fraction"])
    floor = totals["all"]["combined_floor"]
    return {
        "status": "PASS_TRACE_DERIVED_FIXED_ENTRY_BOUND",
        "trace_sha256": free.TRACE,
        "protocol_sha256": free.sha(HERE / "protocol.md"),
        "program_sha256": free.sha(Path(__file__)),
        "whole_prefill_verifier_sha256": FREE_SHA,
        "pr45_snapshot_program_sha256": ORACLE_SHA,
        "pr45_receipt_sha256": free.CERT45,
        "backend": free.PIN,
        "pr45": free.PIN45,
        "source_hashes": baseline["inputs"],
        "stream_source_sha256": free.SOURCE_SHA,
        "graph_source_sha256": free.GRAPH_SHA,
        "snapshot_sha256": {
            f"{kind.lower()}_{call}": hashlib.sha256(
                json.dumps(slots, separators=(",", ":")).encode()
            ).hexdigest()
            for (kind, call), slots in cuts.items()
        },
        "tier_totals": totals,
        "layers": layers,
        "minimum_payload_bytes": floor * free.PAYLOAD,
        "time_scenario": free.decision(floor, budget),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--backend", required=True, type=Path)
    parser.add_argument("--pr45-checkout", required=True, type=Path)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    args = parser.parse_args()
    dest = args.new_output_dir.resolve()
    require(not dest.is_relative_to(args.trace.resolve().parent), "protect raw trace")
    dest.mkdir(exist_ok=False)
    try:
        result = run(args.trace, args.backend, args.pr45_checkout)
    except Exception as exc:
        (dest / "failure.json").write_text(
            json.dumps({"status": "FAIL", "reason": str(exc)}) + "\n"
        )
        raise
    pending = dest / "receipt.pending"
    pending.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    pending.replace(dest / "receipt.json")
    print(result["status"], result.get("time_scenario", {}).get("comparison", ""))
