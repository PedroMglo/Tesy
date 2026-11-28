"""Conditional zero-time envelope for a local CPU FFN in two authenticated nominal conversations."""

import argparse
import json
from collections import Counter, defaultdict
from itertools import groupby
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
SCREEN = run_path(HERE.parents[1] / "screen.py")
SRC, need = SCREEN["SOURCE"], SCREEN["require"]
SCOPES = ("one_miss_decode", "cpu_decode", "cpu_prefill", "cpu_both")
LIMIT = {"first_final": 10_000_000_000, "decode": 47_000_000_000 // 6}


def union_ns(intervals):
    finish = -1
    elapsed = 0
    for a, b in sorted(intervals):
        need(0 <= a <= b, "reversed interval")
        elapsed += max(0, b - max(a, finish))
        finish = max(finish, b)
    return elapsed


def eligibility(call, tiers, waves):
    groups = [list(it) for _, it in groupby(waves, key=lambda w: w.site[:3])]
    geometry = [
        (call["number"], tile, layer)
        for tile in range(1, len(call["geometry"]) + 1)
        for layer in range(36)
        if layer < 35 or (call["number"] > 1 and tile == len(call["geometry"]))
    ]
    need([group[0].site[:3] for group in groups] == geometry, "layer or tile ordering")
    selected = {scope: [] for scope in SCOPES}
    counts = Counter({k: 0 for k in SCOPES})
    prefill = call["number"] <= 2
    for i, group in enumerate(groups):
        if tiers[group[0].site[2]] != "CPU":
            continue
        lo = groups[i - 1][-1].end if i else call["enter_ns"]
        hi = groups[i + 1][0].start if i + 1 < len(groups) else call["return_ns"]
        need(lo <= group[0].start <= group[-1].end <= hi, "callback envelope")
        scopes = ["cpu_both", "cpu_prefill" if prefill else "cpu_decode"]
        if not prefill:
            demands = set.union(*(w.demands for w in group))
            reservations = set.union(*(w.reserved for w in group))
            need(len(demands) == 4, "one token top four")
            if (
                len(reservations) == 1
                and reservations <= demands
                and group[0].start_drained
                and group[-1].end_drained
            ):
                scopes.append("one_miss_decode")
        for s in scopes:
            selected[s].append((lo, hi))
            counts[s] += 1
    credit = {s: union_ns(spans) for s, spans in selected.items()}
    need(
        credit["one_miss_decode"] <= credit["cpu_decode"]
        and credit["cpu_both"] == credit["cpu_prefill"] + credit["cpu_decode"]
        and credit["cpu_both"] <= call["return_ns"] - call["enter_ns"],
        "nested envelopes",
    )
    return counts, credit


def arm(archive, label, prior):
    (summary, first, decode), control = SCREEN["read_arm"](archive, label, prior)
    folder, family, _ = SRC["SOURCES"][label]
    root = archive / ("part-" + label[1:]) / folder
    if label == "P106":
        _, rows, tiers, _ = SRC["Q"]["read_new"](root, family)
    else:
        rows, _ = SRC["T"]["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
        rec = json.loads((root / "ON/receipt.json").read_bytes())
        log = root / "ON/raw" / rec["native_ids"]["raw_stderr_file"]
        tiers, _ = SRC["T"]["mapping"](log.read_bytes(), rows)
    host = SRC["NATIVE"]["host_trace"](rows)
    waves, reservations = SRC["timeline"](rows)
    need(
        len(waves) == control["callbacks"] == 2987 and len(reservations) == control["jobs"] == 2354,
        "service population",
    )
    by_call = defaultdict(list)
    for w in waves:
        by_call[w.site[0]].append(w)
    credit = defaultdict(Counter)
    counts = defaultdict(Counter)
    before = dict(first_final=first, decode=decode)
    for c, s in zip(host["calls"], summary, strict=True):
        need(c["number"] == s.number and s.span == c["return_ns"] - c["enter_ns"], "call identity")
        freq, offered = eligibility(c, tiers, by_call[c["number"]])
        phase = SCREEN["phase"](c["number"])
        counts[phase].update(freq)
        credit[phase].update(offered)
    scopes = {}
    for scope in SCOPES:
        metrics = {}
        for metric, phases in (
            ("first_final", ("prefill", "decode_before_final")),
            ("decode", ("decode_before_final", "decode_tail")),
        ):
            maximum = sum(credit[p][scope] for p in phases)
            floor = before[metric] - maximum
            need(control["outside_calls_ns"][metric] <= floor <= before[metric], "external clock")
            metrics[metric] = dict(
                control_ns=before[metric],
                maximum_credit_ns=maximum,
                floor_ns=floor,
                still_needed_ns=max(0, floor - LIMIT[metric]),
                required_credit_ns=max(0, before[metric] - LIMIT[metric]),
            )
        scopes[scope] = dict(
            metrics=metrics,
            decision="NO_GO_ISOLATED"
            if any(m["still_needed_ns"] for m in metrics.values())
            else "HEADROOM_ONLY",
        )
    return dict(
        journal_sha256=control["journal_sha256"],
        manifest_sha256=control["manifest_sha256"],
        trajectory_sha256=control["trajectory_sha256"],
        jobs=len(reservations),
        callbacks=len(waves),
        calls=len(host["calls"]),
        groups_by_phase=dict(counts),
        union_credit_ns_by_phase=dict(credit),
        outside_calls_ns=control["outside_calls_ns"],
        scopes=scopes,
    )


def run(archive):
    prior = SRC["pinned"](
        SCREEN["NATURAL"] / "prefill_retention/request_cost/receipt.json", SCREEN["PRIOR"]
    )
    return dict(
        evidence="TRACE_DERIVED_CONDITIONAL",
        source_sha256=SRC["digest"](Path(__file__)),
        protocol_sha256=SRC["digest"](HERE / "reach-protocol.md"),
        limits_ns=LIMIT,
        arms={k: arm(archive, k, prior[k]) for k in ("P97", "P106")},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a.archive)
    except Exception as exc:
        (a.new_output_dir / "failure.json").write_text(json.dumps({"error": repr(exc)}) + "\n")
        raise
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    for label, row in result["arms"].items():
        print(label, {s: x["decision"] for s, x in row["scopes"].items()})
