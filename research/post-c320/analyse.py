"""Read immutable C318 receipts and, optionally, the hash-pinned C317 journals."""

import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from statistics import mean

REPO = Path(__file__).resolve().parents[2]
SOURCE = "623a5b97b6e14a39bc671f6d81e7a993a3efe7cb"
C317 = "results/c317-learned-staging-observer-qualification-20261007"
C318 = "results/c318-learned-staging-contemporary-product-cost-20261007"
CASES = ("nominal153", "code153")
FIELDS = "kind us call route layer expert slot gen component bytes rows".split()


def archived(path):
    data = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(REPO), "show", f"{SOURCE}:{path}"]
    )
    return json.loads(data)


def decode_discount(pairs, metric, target):
    """Common fraction of candidate decode removed to reach a paired median gain.

    With exactly two pairs the median is their arithmetic mean. The candidate
    prefill and both R0 arms are fixed. Every gain uses its own R0 denominator.
    """
    if len(pairs) != 2:
        raise ValueError("C318 requires both pairs")
    gain = mean(1 - b[metric] / a[metric] for a, b in pairs)
    slope = mean(b["decode32_s"] / a[metric] for a, b in pairs)
    return (target - gain) / slope


def historical_cost(case, published):
    arms = []
    for index, role in enumerate(("R0", "learned", "learned", "R0"), 1):
        row = archived(f"{C318}/c318-{case}-{index}-{role}-analysis.json")
        if (row["status"], row["case"], row["stage"], row["trace"]) != (
            "PASS_NATIVE_STAGING_COST_ARM",
            case,
            role == "learned",
            False,
        ):
            raise ValueError("unexpected arm identity")
        m = row["metrics"]
        if not all(math.isfinite(v) and v > 0 for v in m.values()) or not math.isclose(
            m["total_s"], m["prefill153_s"] + m["decode32_s"], rel_tol=0, abs_tol=1e-8
        ):
            raise ValueError("invalid phase clocks")
        arms.append(m)
    pairs = [(arms[0], arms[1]), (arms[3], arms[2])]
    for (a, b), original in zip(pairs, published["pairs"], strict=True):
        for metric in ("total_s", "decode32_s", "prefill153_s"):
            gain = 100 * (a[metric] - b[metric]) / a[metric]
            if not math.isclose(gain, original["gain_percent"][metric], abs_tol=1e-8):
                raise ValueError("published pair disagrees with recomputed gain")
    return {
        "total_median_tie_pct_of_candidate_decode": 100 * decode_discount(pairs, "total_s", 0),
        "total_median_8pct_of_candidate_decode": 100 * decode_discount(pairs, "total_s", 0.08),
        "decode_median_15pct_of_candidate_decode": 100 * decode_discount(pairs, "decode32_s", 0.15),
        "arm_metrics_s_ABBA": arms,
    }


def union(intervals):
    merged = []
    for start, end in sorted(intervals):
        if end < start:
            raise ValueError("reversed clock endpoints")
        if end == start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def overlap(left, right):
    """Intersect sorted disjoint half-open intervals from the same clock."""
    i = j = 0
    common = []
    while i < len(left) and j < len(right):
        a, b = left[i]
        c, d = right[j]
        if max(a, c) < min(b, d):
            common.append((max(a, c), min(b, d)))
        if b <= d:
            i += 1
        if d <= b:
            j += 1
    return common


def waiting_generations(stage):
    # Event order distinguishes a real wait even if two timestamps share a microsecond.
    finished = set()
    waiting = set()
    attached_waits = set()
    for e in stage["journal"]:
        ticket = (e["scope"], e["ticket"])
        if e["kind"] == 3:
            finished.add(ticket)
        elif e["kind"] == 6 and ticket not in finished:
            attached_waits.add(ticket)
        elif e["kind"] == 7 and ticket in attached_waits:
            if ticket not in finished:
                raise ValueError("copy claimed before producer completed")
            attached_waits.remove(ticket)
            work = (e["call"], e["layer"], e["expert"], e["slot"], e["generation"])
            if work in waiting:
                raise ValueError("duplicate primary generation")
            waiting.add(work)
    if attached_waits or len(waiting) != stage["stats"]["waits"]:
        raise ValueError("journal does not reconcile to all counted waits")
    return waiting


def summarize_trace(primary, stage):
    fields, *lines = primary.splitlines()
    if fields.split() != FIELDS:
        raise ValueError("unknown events.tsv schema")
    waiting = waiting_generations(stage)
    enqueued, dequeued, first_copy, barrier_start = {}, {}, {}, {}
    barriers = []
    for line in lines:
        e = dict(zip(FIELDS, map(int, line.split()), strict=True))
        call, layer, kind, us = e["call"], e["layer"], e["kind"], e["us"]
        if call == 0:
            continue  # prefill precedes prediction_begin
        work = (call, layer, e["expert"], e["slot"], e["gen"])
        route = (call, layer, e["route"])
        if kind == 4:
            enqueued.setdefault(work, us)
        elif kind == 5:
            dequeued[work] = us
        elif kind == 8 and e["component"] == 0:
            first_copy[work] = us
        elif kind == 11:
            if route in barrier_start:
                raise ValueError("nested wait for the same route")
            barrier_start[route] = us
        elif kind == 12:
            barriers.append((barrier_start.pop(route), us))
    if barrier_start or waiting - first_copy.keys() or waiting - dequeued.keys():
        raise ValueError("incomplete duration or generation join")
    # All durations are now on the PRIMARY clock. The staging clock is never subtracted.
    occupied = [(dequeued[w], first_copy[w]) for w in waiting]
    queue = union((enqueued[w], us) for w, us in dequeued.items())
    wall = union(occupied)
    simultaneous = overlap(overlap(wall, queue), union(barriers))
    return {
        "attached_while_reading": len(waiting),
        "gross_dequeue_to_first_copy_worker_us": sum(b - a for a, b in occupied),
        "gross_dequeue_to_first_copy_wall_us": sum(b - a for a, b in wall),
        "overlap_with_accepted_queue_and_router_wait_wall_us": sum(b - a for a, b in simultaneous),
    }


def required_files():
    manifest = archived(f"{C317}/raw-manifest.json")["files"]
    selected = {}
    for case in CASES:
        for arm in (2, 3):
            for name in ("events.tsv", "staging.json"):
                rel = f"c317-{case}-{arm}-trace.native/{name}"
                (entry,) = (row for row in manifest if row["path"] == f"{C317}/raw/{rel}")
                selected[rel] = {"size_bytes": entry["size_bytes"], "sha256": entry["sha256"]}
    return selected


def checked_bytes(path, receipt):
    if path.stat().st_size != receipt["size_bytes"]:
        raise ValueError(f"size mismatch: {path.name}")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != receipt["sha256"]:
        raise ValueError(f"SHA-256 mismatch: {path.name}")
    return data


def prefill_union_sizes():
    layers = archived("results/c261-slots40-prefill-opportunity-20261004/analysis.json")["layers"]
    if sorted(layer["layer"] for layer in layers) != list(range(36)):
        raise ValueError("C261 layer inventory is incomplete")
    counts = {"CPU": [], "CUDA0": []}
    for layer in layers:
        experts = layer["demanded_union"]
        if len(experts) != len(set(experts)) or len(experts) != layer["union_count"]:
            raise ValueError("union cardinality disagrees with logical IDs")
        counts[layer["tier"]].append(len(experts))
    return {
        tier: {
            "layers": len(sizes),
            "above_40": sum(n > 40 for n in sizes),
            "min": min(sizes),
            "max": max(sizes),
        }
        for tier, sizes in counts.items()
    }


def report(raw_dir):
    c136 = archived("results/c135-slots40-warm153-trace-20260929T2205Z/analysis.json")["server"][
        "trace_off"
    ]
    published = archived(f"{C318}/paired-cost-analysis.json")["cases"]
    inputs = required_files()
    result = {
        "source_commit": SOURCE,
        "C261_whole_prefill_distinct_experts_per_layer": prefill_union_sizes(),
        "C136_fixed_work_scenario_s": {
            "first_final_less_entire_decode": c136["warm_first_final_s"] - c136["warm_decode_s"],
            "decode_saving_needed_for_6_tps": c136["warm_decode_s"]
            - c136["warm_output_tokens"] / 6,
            "prefill_alone": c136["warm_prefill_s"],
        },
        "C318_conditional_arithmetic": {c: historical_cost(c, published[c]) for c in CASES},
        "C317_inputs_relative_to_raw_dir": inputs,
        "occupancy": "NOT_RUN_RAW_REQUIRED",
        "counterfactual_speedup": None,
    }
    if raw_dir is not None:
        data = {rel: checked_bytes(raw_dir / rel, receipt) for rel, receipt in inputs.items()}
        observers = archived(f"{C317}/observer-analysis.json")["cases"]
        traces = {}
        for case in CASES:
            for arm in (2, 3):
                name = f"c317-{case}-{arm}-trace.native"
                traces[name] = summarize_trace(
                    data[f"{name}/events.tsv"].decode(), json.loads(data[f"{name}/staging.json"])
                )
                traces[name]["historical_case_timing_neutral"] = observers[case]["neutral_timing"]
        result["occupancy"] = {"classification": "TRACE_DERIVED_DIAGNOSTIC", "arms": traces}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, help="unchanged C317 raw/ directory")
    options = parser.parse_args()
    try:
        print(json.dumps(report(options.raw_dir), indent=2, allow_nan=False))
    except (KeyError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        sys.exit(f"INCOMPLETE_EVIDENCE: {exc}")
