"""Certify a client time floor for every choice of two last-loss captures per pipeline stage."""

import argparse
import os
from collections import defaultdict
from functools import cache
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
A = run_path(HERE / "retention.py")
E, R, T, S, need, sha, save, verified, F = (
    A[k] for k in ("E", "R", "T", "S", "need", "sha", "save", "verified", "F")
)
K = T["K"]
P = K["P"]
NS = 10**9
CAP = 2


def paths():
    stages = {}
    for tile in range(1, 6):
        for side in (0, 1):
            node = tile, side
            pred = [(tile - 1, 0), (tile - 2, 1)] if not side else [(tile, 0), (tile - 1, 1)]
            base = {p for n in pred if n in stages for p in stages[n]}
            stages[node] = {p + (node,) for p in (base or {()})}
    return sorted(stages[5, 1])


def best(intervals, reward, capacity):
    starts = defaultdict(list)
    ends = defaultdict(set)
    for iv in intervals:
        starts[iv.start].append(iv)
        ends[iv.end].add(iv)
    states = {(): 0}
    for at in sorted(starts.keys() | ends.keys()):
        if at in ends:
            ending = ends[at]
            merged = {}
            for live, value in states.items():
                done = tuple(v for v in live if v in ending)
                survivors = tuple(v for v in live if v not in ending)
                amount = value + (reward(done) if done else 0)
                merged[survivors] = max(merged.get(survivors, 0), amount)
            states = merged
        for new in starts.get(at, ()):
            added = {live + (new,): v for live, v in states.items() if len(live) < capacity}
            states.update(added)
    need(states.keys() == {()}, "all parking released")
    return states[()]


def charge(rows, resident, coupled):
    times = [st + (rd if e not in resident and e not in coupled else 0) for e, rd, st in rows]
    return max(max(times), (sum(times) + 3) // 4)


def audit(tag, data, marks, layout, base, opps, previous):
    # The clock of a layer's READ/SET region always belongs to a single stage.
    chunks = {(0, 0): marks["calls"][0]}
    for tile, (_, a, b, c, d, _) in enumerate(marks["tiles"], 1):
        chunks[tile, 0] = a, b
        chunks[tile, 1] = c, d
    loc = {}
    free = defaultdict(list)
    for call, tile, layer, lo, start, end, hi, work in data["groups"]:
        if call > 2:
            continue
        site = call, tile, layer
        baseline, coupled, *_ = K["sources"](work, layout[layer], base.get(site, ()))
        active = bool(baseline or coupled)
        if active:
            free[call].append((lo, hi))
        loc[site] = (lo, start, end, hi, work, baseline, coupled, active)
    stage_base = {}
    for step, (a, b) in chunks.items():
        call = 2 if step[0] else 1
        val = P["kept"](a, b, free[call])
        for site, (_, s, e, _, rows, hot, coupled, active) in loc.items():
            if site[0] != call or not active or e <= a or s >= b:
                continue
            need(a <= s < e <= b, "split service in baseline")
            val += charge(rows, hot, coupled)
        stage_base[step] = val

    def span(c, n):
        return P["ceil_div"](c * T["PAYLOAD"] * NS, n)

    rate = int(R["RATE"])
    c1 = max(stage_base[0, 0], span(34, rate))
    basepath = P["pipeline"]([(stage_base[i, 0], stage_base[i, 1]) for i in range(1, 6)])[-1][-1]
    need(c1 + max(basepath, span(858, rate)) == previous["prefill_ns"], "exact disabled chronology")

    # A site can overlap another site's outer interval. For a selected path,
    # at most this much previously uncovered wall time can disappear. Any
    # newly incurred service floor is charged only where the path contains it.
    site_for = {iv: r.site for iv, (_, r) in opps.items()}

    def lower(path, cap):
        selected_chunks = frozenset(path)

        @cache
        def gain(done):
            site = site_for[done[0]]
            need(all(site_for[v] == site for v in done), "different sites at one release")
            lo, s, e, hi, work, hot, coupled, active = loc[site]
            new = hot | {v.expert for v in done}
            saved = 0
            for step in selected_chunks:
                a, b = chunks[step]
                if not active and max(a, lo) < min(b, hi):
                    saved += P["kept"](max(a, lo), min(b, hi), free[2])
                if max(a, s) < min(b, e):
                    need(a <= s < e <= b, "split paid service")
                    saved += (charge(work, hot, coupled) if active else 0) - charge(
                        work, new, coupled
                    )
            return max(0, saved)

        total = 0
        for group in (0, 1):
            eligible = [iv for iv in opps if T["stage"](iv.layer) == group]
            total += best(eligible, gain, cap)
        return sum(stage_base[step] for step in path) - total

    proof = []
    for path in paths():
        before = sum(stage_base[n] for n in path)
        proof.append(
            dict(path=[list(node) for node in path], before_ns=before, lower_ns=lower(path, CAP))
        )
    need(max(v["before_ns"] for v in proof) == basepath, "path enumeration")
    possible = [{iv for iv in opps if T["stage"](iv.layer) == s} for s in (0, 1)]
    maximum = sum(len(R["maximum"](items, CAP)) for items in possible)
    disk = span(858 - maximum, rate)
    floor = c1 + max(disk, max(v["lower_ns"] for v in proof))
    return dict(journal=tag, call1_ns=c1, call2_bandwidth_ns=disk, paths=proof, prefill_ns=floor)


def run(inputs):
    parent = verified(
        HERE.parent / "evidence-entry-20261128-r01/receipt.json", A["P"]["P"]["ENTRY"]
    )
    prior = verified(HERE.parent / "evidence-20261128-r01/receipt.json", parent["prior"])
    finite = verified(inputs, "807015e2a44d35068b7676308a19ca19b8f050f3a335acdd210f2a7215f4fa87")
    tx = verified(S["PATHS"]["transactions"], prior["sources"]["transactions"])
    service = verified(S["PATHS"]["service"], prior["sources"]["service"])
    cfg = {k: verified(T["E"] / (k + ".json"), h) for k, h in prior["geometry"].items()}
    base, *_ = E["inventory"](tx)
    opps = A["demand_intervals"](A["events"](tx))
    need(len(opps) == 166 and {r.site[0] for _, r in opps.values()} == {2}, "cold intervals")
    results = {}
    arms = []
    for tag, raw in service["journals"].items():
        original = [a for a in prior["arms"]["off"] if a["tag"] == tag]
        bound = audit(
            tag,
            raw,
            cfg["pipeline"]["arms"][tag]["markers"],
            cfg["plan"]["order"],
            base,
            opps,
            original[0],
        )
        floor = bound["prefill_ns"]
        seen = [
            r["prefill_ns"]
            for mode, rows in finite["prices"].items()
            if mode != "unlimited"
            for r in rows
            if r["tag"] == tag and r["pairs"] == "free_original_pairs"
        ]
        need(floor <= min(seen), "finite witness beats optimistic proof")
        ideal = next(a["prefill_ns"] for a in parent["arms"] if a["tag"] == tag)
        # Two independent lower bounds may be combined by their maximum.
        floor = max(floor, ideal)
        results[tag] = bound | dict(unlimited_ns=ideal, combined_ns=floor)
        for r in original:
            ff = [v + floor - r["prefill_ns"] for v in r["first_ns"]]
            arms.append(
                dict(
                    tag=tag,
                    W=r["W"],
                    repeat=r["repeat"],
                    first_ns=ff,
                    decode_ns=r["decode_ns"],
                    common_slack_ns=min(10**10 - ff[1], 47 * NS // 6 - r["decode_ns"]),
                )
            )
    verdict = A["P"]["M"]["P"]["decision"](arms)
    return dict(
        status=verdict if verdict == "NO_GO" else "INCONCLUSIVE",
        journals=results,
        arms=arms,
        evidence="FORMAL_CONDITIONAL_ON_FIXED_SERVICE_PRICES",
        intervals=len(opps),
        protocol=sha(HERE / "bound.md"),
        program=sha(Path(__file__)),
        finite=sha(inputs),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--finite", required=True, type=Path)
    dest = p.add_mutually_exclusive_group(required=True)
    dest.add_argument("--check", type=Path)
    dest.add_argument("--new-output-dir", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        result = run(a.finite)
        if a.check:
            need(result == F["load"](a.check), "changed proof")
        else:
            save(a.new_output_dir / "receipt.json", result)
        print(result["status"], [(k, v["combined_ns"]) for k, v in result["journals"].items()])
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise


if __name__ == "__main__":
    main()
