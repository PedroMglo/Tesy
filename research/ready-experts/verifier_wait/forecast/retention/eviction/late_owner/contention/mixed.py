"""Partition each surviving target READ by its observed competitors in the same process."""

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
V = run_path(HERE / "victims.py")
F, C, need, sha, save = (V[k] for k in ("F", "C", "need", "sha", "save"))
METHOD = "09d49dd67c8d59fc42e938ea5b0024f9521fc1ab53e5f7e3a9597ad96d27351f"
ORIGINAL = HERE / "evidence-20261128-r01"


def split(rows, hits, *, on_interval=None):
    boundaries = defaultdict(lambda: (set(), set()))
    for i, row in enumerate(rows, 1):
        boundaries[row[5]][1].add(i)
        boundaries[row[6]][0].add(i)
    area = defaultdict(Counter)
    by_layer = defaultdict(Counter)
    shape_jobs = defaultdict(set)
    live = set()
    left = None
    first = {}
    overlap, twelfths, served = Counter(), Counter(), Counter()
    for right, (stop, start) in sorted(boundaries.items()):
        if live:
            q, k = len(live), len(live & hits)
            need(q <= 4, "four reader maximum")
            width = right - left
            if on_interval is not None:
                on_interval(live, q, k, width)
            shape = f"{q}/{k}"
            group = area[shape]
            same = len({tuple(rows[i - 1][1][:3]) for i in live}) == 1
            group.update(
                wall_ns=width,
                hit_worker_ns=width * k,
                survivor_worker_ns=width * (q - k),
                cross_site_wall_ns=width * int(not same),
            )
            for i in live:
                served[i] += width
                if i in hits:
                    continue
                r = rows[i - 1]
                phase = C["phase"](r[1][0])
                by_layer[phase, r[0][0]][shape] += width
                shape_jobs[shape].add(i)
                if k:
                    overlap[i] += width
                    twelfths[i] += width * k * (12 // q)
                    first.setdefault(i, left)
        need(stop <= live and not start & live, "interval events")
        live.difference_update(stop)
        live.update(start)
        left = right
    need(
        not live and all(served[i] == r[6] - r[5] for i, r in enumerate(rows, 1)),
        "READ reconstruction",
    )
    suffix = {i: rows[i - 1][6] - t for i, t in first.items()}
    whole = {i: served[i] for i in overlap}
    fair = {i: n // 12 for i, n in twelfths.items()}
    need(
        all(0 <= fair[i] <= overlap[i] <= suffix[i] <= whole[i] for i in overlap),
        "nested timing supports",
    )
    need(
        sum(served.values())
        == sum(v["hit_worker_ns"] + v["survivor_worker_ns"] for v in area.values())
        and sum(sum(v.values()) for v in by_layer.values())
        == sum(n for i, n in served.items() if i not in hits),
        "worker-time and layer conservation",
    )
    for shape, census in area.items():
        census["distinct_survivors"] = len(shape_jobs[shape])
    return (
        dict(equal_share=fair, simultaneous=dict(overlap), suffix=suffix, whole=whole),
        dict(
            shapes=area,
            survivor_ns_by_phase_and_layer=[
                [phase, layer, counts] for (phase, layer), counts in sorted(by_layer.items())
            ],
        ),
    )


def evaluate():
    need(sha(HERE / "mixed-protocol.md") == METHOD, "registered protocol")
    meta = json.loads((ORIGINAL / "provenance.json").read_bytes())
    for n in ("service.json.gz", "victims.json"):
        need(sha(ORIGINAL / n) == meta["artifacts"][n]["sha256"], "frozen input")
    raw = F["unpack"](ORIGINAL / "service.json.gz")
    earlier = json.loads((ORIGINAL / "victims.json").read_bytes())
    basis, _, _ = F["freeze"]()
    tx, effect = V["sources"]()
    hits = {i for i, e in enumerate(effect, 1) if e[1] is not None}
    need(len(hits) == 674, "renewable bank")
    result = {}
    for tag, observed in raw.items():
        arm = basis["arms"][tag]
        jobs = observed["jobs"]
        for j, (call, tile, layer, slot, gen, expert, _) in zip(jobs, tx, strict=True):
            need(
                j[0] == [layer, slot, gen, expert] and j[1][:3] == [call, tile, layer], "generation"
            )
        credits, population = split(jobs, hits)
        previous = earlier["arms"][tag]
        total = sum(v["peers"] for v in previous["eligible"]["any_peer"].values())
        need(len(credits["whole"]) == total, "peer identity coverage")
        modes = {}
        for name, placed in (("paid", False), ("favorable", True)):
            modes[name] = {
                key: V["priced_case"](arm, hits, placed, tag, amounts)
                for key, amounts in credits.items()
            }
            need(
                modes[name]["whole"] == previous["modes"][name]["cases"]["any_peer"],
                "previous break-even and full clocks",
            )
        result[tag] = dict(
            population=population,
            eligible_worker_ns={k: sum(v.values()) for k, v in credits.items()},
            modes=modes,
        )
    joint = {}
    for name in ("paid", "favorable"):
        joint[name] = {}
        for key in ("equal_share", "simultaneous", "suffix", "whole"):
            both = [r["modes"][name][key] for r in result.values()]
            margin = min(V["budget"](c["full"]) for c in both)
            joint[name][key] = dict(
                full_margin_ns=margin, decision="NO_GO" if margin < 0 else "GO_COST_FIXTURE"
            )
            if margin >= 0:
                joint[name][key]["min_reduction_ppm"] = max(c["min_reduction_ppm"] for c in both)
    return dict(
        evidence="TRACE_DERIVED_CONDITIONAL",
        method=METHOD,
        prior=sha(ORIGINAL / "victims.json"),
        arms=result,
        joint=joint,
        http_requests=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    out = parser.add_mutually_exclusive_group(required=True)
    out.add_argument("--new-output-dir", type=Path)
    out.add_argument("--check", type=Path)
    a = parser.parse_args()
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        grade = evaluate()
        if a.check:
            need(grade == json.loads(a.check.read_bytes()), "published mixed clocks")
        else:
            save(a.new_output_dir / "mixed.json", grade)
        print(grade["joint"])
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise
