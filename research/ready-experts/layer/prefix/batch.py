"""Bound exact coalescing of adjacent expert records without changing an on-disk weight."""

import argparse
import json
from collections import Counter, defaultdict
from itertools import chain, combinations, groupby
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
reach = run_path(HERE / "reach.py")
SCREEN, SRC, need, LIMIT = (reach[k] for k in ("SCREEN", "SRC", "need", "LIMIT"))
PHASES = {
    "prefill": ("prefill",),
    "first_final": ("prefill", "decode_before_final"),
    "decode": ("decode_before_final", "decode_tail"),
}


def certificate(batches, vertices=128):
    pairs = Counter()
    incidence = defaultdict(list)
    requests = duplicated = per_batch = 0
    for batch in batches:
        distinct = sorted(set(batch))
        need(all(0 <= e < vertices for e in distinct), "expert index")
        requests += len(batch)
        duplicated += len(batch) - len(distinct)
        per_batch += max(0, len(distinct) - 1)
        pairs.update(combinations(distinct, 2))
    for (i, j), price in pairs.items():
        incidence[i].append(price)
        incidence[j].append(price)
    degree_cap = sum(sum(sorted(p, reverse=True)[:2]) for p in incidence.values()) // 2
    path_cap = sum(sorted(pairs.values(), reverse=True)[: vertices - 1])
    ordinary = sum(n for (i, j), n in pairs.items() if j == i + 1)
    bound = min(degree_cap, path_cap, per_batch)
    need(0 <= ordinary <= bound <= requests - duplicated, "adjacency certificate")
    return dict(
        generations=requests,
        repeated=duplicated,
        numeric_adjacent=ordinary,
        path_cap=path_cap,
        degree_cap=degree_cap,
        batch_cap=per_batch,
        command_saving_upper=bound + duplicated,
    )


def arm(archive, label, prior):
    (_, first, decode), control = SCREEN["read_arm"](archive, label, prior)
    folder, h, _ = SRC["SOURCES"][label]
    root = archive / ("part-" + label[1:]) / folder
    if label == "P97":
        rows, _ = SRC["T"]["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
    else:
        _, rows, _, _ = SRC["Q"]["read_new"](root, h)
    host = SRC["NATIVE"]["host_trace"](rows)
    waves, orig = SRC["timeline"](rows)
    by_call = defaultdict(list)
    for w in waves:
        by_call[w.site[0]].append(w)
    batches = defaultdict(lambda: defaultdict(list))
    credit = Counter()
    eligible = Counter()
    used = set()
    for call in host["calls"]:
        num = call["number"]
        phase = SCREEN["phase"](num)
        groups = [list(it) for _, it in groupby(by_call[num], key=lambda w: w.site[:3])]
        spans = []
        for i, group in enumerate(groups):
            generations = [k for w in group for k in w.reserved]
            need(
                not used.intersection(generations) and len(generations) == len(set(generations)),
                "duplicate reservation",
            )
            used.update(generations)
            ids = [k[3] for k in generations]
            layer = group[0].site[2]
            need(all(k[0] == layer for k in generations), "layer boundary")
            batches[phase][layer].append(ids)
            if len(set(ids)) >= 2:
                lo = groups[i - 1][-1].end if i else call["enter_ns"]
                hi = groups[i + 1][0].start if i + 1 < len(groups) else call["return_ns"]
                need(lo <= group[0].start <= group[-1].end <= hi, "chronology")
                spans.append((lo, hi))
        credit[phase] += reach["union_ns"](spans)
        eligible[phase] += len(spans)
    need(used == orig.keys() and len(used) == control["jobs"] == 2354, "reservation coverage")
    report = {}
    for scope, phases in PHASES.items():
        counts = Counter()
        for layer in range(36):
            counts.update(certificate(chain.from_iterable(batches[p][layer] for p in phases)))
        if scope == "prefill":
            report[scope] = dict(counts=counts)
            continue
        before = first if scope == "first_final" else decode
        maximum = sum(credit[p] for p in phases)
        floor = before - maximum
        need(control["outside_calls_ns"][scope] <= floor <= before, "clock conservation")
        need(counts["command_saving_upper"] > 0, "no possible command saving")
        required = max(0, before - LIMIT[scope])
        report[scope] = dict(
            counts=counts,
            control_ns=before,
            maximum_credit_ns=maximum,
            floor_ns=floor,
            still_needed_ns=max(0, floor - LIMIT[scope]),
            required_mean_ns_per_command=(required + counts["command_saving_upper"] - 1)
            // counts["command_saving_upper"],
        )
    return dict(
        decision="NO_GO_ISOLATED"
        if any(report[c]["still_needed_ns"] for c in LIMIT)
        else "HEADROOM_ONLY",
        scopes=report,
        eligible_regions_by_phase=eligible,
        unique_interval_ns_by_phase=credit,
        journal_sha256=control["journal_sha256"],
        manifest_sha256=control["manifest_sha256"],
        generations=len(used),
        weight_bytes=len(used) * 13219200,
    )


def run(archive):
    prior = SRC["pinned"](
        SCREEN["NATURAL"] / "prefill_retention/request_cost/receipt.json", SCREEN["PRIOR"]
    )
    return dict(
        evidence="TRACE_DERIVED_CONDITIONAL",
        source_sha256=SRC["digest"](Path(__file__)),
        protocol_sha256=SRC["digest"](HERE / "batch-protocol.md"),
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
    for k, v in result["arms"].items():
        print(k, v["decision"])
