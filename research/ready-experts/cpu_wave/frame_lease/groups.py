"""Compare one promoted expert and simultaneous promotions at the same consumer barrier."""

import argparse
import gzip
import json
import os
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
L = run_path(HERE / "lifetime.py")
need, sha, encode = (L[k] for k in ("need", "sha", "encode"))
METHOD = "6d3438587b6fdeaf82aacb5c1c4ab99a1796aecbedf7e51f070d35bb56c588f1"
PRIOR = "111e377c305802d15917d3b3d8cb3462c126e3ae633fc72ce383a76ddec4f2c8"
SCENARIOS = ("remove_sets", "remove_read_and_sets", "ready_on_entry")


def contrast(start, published, changed):
    """All publication times share this journal clock and every competing rank stays in the max."""
    need(changed and all(t <= published[k] for k, t in changed.items()), "invalid substitution")
    peak = max(start, max(published.values(), default=start))
    individual = [
        peak - max([start, t, *(pub for other, pub in published.items() if other != k)])
        for k, t in changed.items()
    ]
    group = peak - max(start, max((changed.get(k, t) for k, t in published.items()), default=start))
    best, separate = max(individual), sum(individual)
    need(0 <= best <= separate <= group <= peak - start, "unpaid work or counted a waiter twice")
    return dict(group_ns=group, best_one_ns=best, individual_sum_ns=separate)


def fault_controls():
    tied = contrast(100, {1: 109, 2: 109, 3: 103}, {1: 100, 2: 100})
    need(tied == dict(group_ns=6, best_one_ns=0, individual_sum_ns=0), "tied producers")
    hidden = contrast(100, {1: 109, 2: 111, 3: 114}, {1: 100, 2: 100})
    ready = contrast(100, {1: 94, 2: 88}, {1: 91, 2: 80})
    need(all(v == 0 for test in (ready, hidden) for v in test.values()), "hidden delivery")
    return dict(tied=tied, fixed_slower_peer=hidden, already_ready=ready)


def arm(windows, service, actions, previous):
    jobs = service["jobs"]
    by_key = {tuple(j[0]): i for i, j in enumerate(jobs)}
    barriers = {tuple(site): (start, end, last) for site, start, end, last in service["last"]}
    need(
        len(by_key) == len(jobs) == 2354 and len(barriers) == len(service["last"]),
        "unique native bindings",
    )
    hits = {i for i, a in actions.items() if a[2]}
    seen = set()
    rows = []
    prev_remap_end = 0
    for site, remap_start, remap_end, demand in windows["cpu"]:
        need(remap_start >= prev_remap_end, "overlapping consumer clocks")
        prev_remap_end = remap_end
        demanded_jobs = {by_key[tuple(k)] for k in demand if tuple(k) in by_key}
        first = sorted((demanded_jobs & hits) - seen)
        seen.update(first)
        if not first:
            continue
        bounds = barriers.get(tuple(site))
        row = dict(
            site=site,
            first=first,
            demand=len(demand),
            wait_ns=0,
            tied_last=0,
            last_hit_count=0,
            wakeup_ns=None,
        )
        if bounds:
            start, end, last = bounds
            published = {i: jobs[i][-1] for i in demanded_jobs}
            peak = max(published.values())
            last_ids = {by_key[tuple(k)] for k in last}
            need(
                remap_start <= start < peak <= end <= remap_end
                and {i for i, t in published.items() if t == peak} == last_ids,
                "unmatched last native publication",
            )
            row.update(
                wait_ns=peak - start,
                tied_last=len(last_ids),
                last_hit_count=len(last_ids.intersection(first)),
                wakeup_ns=end - peak,
            )
            no_sets, no_io = {}, {}
            for i in first:
                j = jobs[i]
                sets = sum(j[k + 1] - j[k] for k in (7, 9, 11))
                read = j[6] - j[5]
                no_sets[i] = published[i] - sets
                no_io[i] = no_sets[i] - read
                need(0 < sets and 0 < read and j[2] <= no_io[i] <= no_sets[i], "service order")
            replacements = (no_sets, no_io, {i: min(start, published[i]) for i in first})
            for name, change in zip(SCENARIOS, replacements, strict=True):
                row[name] = contrast(start, published, change)
            need(
                row[SCENARIOS[0]]["group_ns"]
                <= row[SCENARIOS[1]]["group_ns"]
                <= row[SCENARIOS[2]]["group_ns"],
                "non-monotone credits",
            )
        else:
            # The source records every barrier whose demand includes a post-entry publication.
            for name in SCENARIOS:
                row[name] = dict(group_ns=0, best_one_ns=0, individual_sum_ns=0)
        rows.append(row)
    need(seen == hits and len(hits) == 469, "first use of every original promotion")
    totals = {p: {kind: {} for kind in ("grouped", "single")} for p in L["PHASES"]}
    for phase, kinds in totals.items():
        for kind, result in kinds.items():
            subset = [
                r
                for r in rows
                if L["phase"](r["site"][0]) == phase
                and (len(r["first"]) > 1) == (kind == "grouped")
            ]
            result.update(
                waves=len(subset),
                hits=sum(len(r["first"]) for r in subset),
                waited=sum(r["wait_ns"] > 0 for r in subset),
                ties=sum(r["tied_last"] > 1 for r in subset),
                native_wait_ns=sum(r["wait_ns"] for r in subset),
                wakeup_after_publish_ns=sum(r["wakeup_ns"] or 0 for r in subset),
            )
            for name in SCENARIOS:
                values = [r[name] for r in subset]
                out = {
                    key: sum(v[key] for v in values)
                    for key in ("group_ns", "best_one_ns", "individual_sum_ns")
                }
                out["positive_waves"] = sum(v["group_ns"] > 0 for v in values)
                out["beyond_one_waves"] = sum(v["group_ns"] > v["best_one_ns"] for v in values)
                out["excess_over_sum_ns"] = out["group_ns"] - out["individual_sum_ns"]
                result[name] = out
        old = previous["phases"][phase]
        need(
            kinds["grouped"]["waves"] == old.get("grouped_callbacks", 0)
            and kinds["grouped"]["hits"] == old.get("grouped_promotions", 0)
            and kinds["grouped"]["hits"] + kinds["single"]["hits"] == old["first_uses"],
            "conservation against independently graded first uses",
        )
    return rows, totals


def evaluate():
    need(sha(HERE / "group-protocol.md") == METHOD, "registered group protocol")
    parent = HERE / "evidence-lifetime-20261128-r01"
    previous = L["F"]["SRC"]["pinned"](parent / "decision.json", PRIOR)
    need(
        sha(parent / "waves.json.gz") == previous["compressed_windows_sha256"],
        "original consumer windows",
    )
    windows = L["F"]["unpack"](parent / "waves.json.gz")
    _, _, actions, service, _ = L["inputs"]()
    rows, totals = {}, {}
    for tag, data in windows.items():
        rows[tag], totals[tag] = arm(data, service[tag], actions, previous["journals"][tag])
    examples, cpu0 = {}, []
    positive_both = Counter()
    for a, b in zip(rows["P97"], rows["P106"], strict=True):
        need(
            all(a[k] == b[k] for k in ("site", "first", "demand")),
            "sites or generations changed across journals",
        )
        site = a["site"]
        if len(a["first"]) < 2:
            continue
        phase = L["phase"](site[0])
        descriptor = dict(
            site=site,
            count=len(a["first"]),
            reservation_indexes=a["first"],
            original_demand=a["demand"],
            prices={k: {s: r[s] for s in SCENARIOS} for k, r in (("P97", a), ("P106", b))},
        )
        if site in ([2, 5, 0, 2], [11, 1, 0, -1]):
            cpu0.append(descriptor)
        if phase == "tail":
            continue
        for name in SCENARIOS:
            if all(r[name]["group_ns"] > r[name]["best_one_ns"] for r in (a, b)):
                positive_both[name] += 1
                if name == "remove_sets" and (
                    phase not in examples or examples[phase]["count"] > descriptor["count"]
                ):
                    examples[phase] = descriptor
    need(len(cpu0) == 2 and {r["count"] for r in cpu0} == {4, 9}, "registered CPU0 sites")
    ideal = sum(
        t[p]["grouped"]["ready_on_entry"]["group_ns"]
        for t in totals.values()
        for p in L["PHASES"][:3]
    )
    if positive_both["remove_sets"]:
        decision = "GO_GROUP_SERVICE_FIXTURE"
    elif ideal == 0:
        decision = "NO_GO_HIDDEN_GROUP_DELIVERY"
    else:
        decision = "INCONCLUSIVE_GROUP_SERVICE"
    return dict(
        protocol_sha256=METHOD,
        parent_sha256=PRIOR,
        status=decision,
        evidence="CONDITIONAL_LOCAL_BARRIER_FIXED_NATIVE_CLOCKS",
        phases=totals,
        beyond_one_in_same_wave_both_journals=positive_both,
        smallest_same_wave_examples=examples,
        registered_CPU0=cpu0,
        controls=fault_controls(),
        product_gain_ns=None,
        model_forwards=0,
        HTTP_requests=0,
    ), rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    dest = p.add_mutually_exclusive_group(required=True)
    dest.add_argument("--check", type=Path)
    dest.add_argument("--new-output-dir", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        decision, rows = evaluate()
        raw = encode(rows)
        if a.check:
            need(
                raw == gzip.decompress((a.check / "barriers.json.gz").read_bytes())
                and decision == json.loads((a.check / "decision.json").read_bytes()),
                "per-wave prices or decision changed",
            )
        else:
            (a.new_output_dir / "barriers.json.gz").write_bytes(gzip.compress(raw, mtime=0))
            (a.new_output_dir / "decision.json").write_text(
                json.dumps(decision, indent=2, sort_keys=True) + "\n"
            )
        print(decision["status"], dict(decision["beyond_one_in_same_wave_both_journals"]))
    except Exception as exc:
        if a.new_output_dir:
            (a.new_output_dir / "FAIL.json").write_text(json.dumps({"error": repr(exc)}) + "\n")
        raise


if __name__ == "__main__":
    main()
