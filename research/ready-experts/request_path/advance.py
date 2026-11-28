"""Necessary cross-router coverage under measured group prices and free transfers."""

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
L = run_path(HERE / "layer_release.py")
G, T, R, sha, need = (L[k] for k in ("G", "T", "R", "sha", "need"))
PRIOR = HERE / "evidence-layer-20261128-r01"
METHOD = "2e0e8c19126435a933921806238cd4876623bb2f9370b62c7fa5188095b93f28"
READS = "925e9d6ec7c1cef5480ff4ade583221bbf3c664096e032e42b442b83640d3fd5"
PARENT = "d00f5d0ab791b60d79f8f3dc1b5023cbb536628ee198e0dae73651fe38c15fc9"


def previous_visit(obs, words, chosen):
    by_group = defaultdict(set)
    for _, i, _, _, expert in chosen:
        need(expert not in by_group[i], "duplicate compulsory expert in a routed layer")
        by_group[i].add(expert)
    previous, groups = {}, set()
    count = Counter()
    for (site, rows), (key, words_now) in zip(L["sites"](obs), words, strict=True):
        group = rows[0][0]
        layer = site[2]
        need(list(site) == key, "source layer")
        demand = by_group.get(group, set())
        first = layer not in previous
        forecast = demand if first else previous[layer]
        available = forecast & demand
        count["free_entry_hits" if first else "previous_hits"] += len(available)
        if available:
            groups.add(group)
            count["first_groups" if first else "repeated_groups"] += 1
        previous[layer] = {e for word in words_now for e in word.to_bytes(4, "little")}
    return groups, dict(count)


def per_arm(obs, times, eligible):
    control = L["layer_prices"](obs, times)["next_router"]
    credits = []
    all_credit = Counter(dict.fromkeys(R["PHASES"], 0))
    for i, phase, _, _, rest in L["layer_windows"](obs):
        debt = max(0, times.get(i, 0) - rest)
        if i in eligible:
            all_credit[phase] += debt
        if phase != "decode_tail" and debt:
            credits.append((debt, i))
    ranked = sorted(credits, key=lambda item: (-item[0], item[1]))
    need(control["decode_margin"] >= 0 and control["first_margin"] < 0, "unexpected binding clock")
    target = -control["first_margin"]
    prefix = 0
    picked = []
    before = 0
    for debt, i in ranked:
        before = prefix
        prefix += debt
        picked.append(i)
        if prefix >= target:
            break
    need(before < target <= prefix, "insufficient even with all groups")
    reduced = {i: s for i, s in times.items() if i not in eligible}
    favorable = L["layer_prices"](obs, reduced)["next_router"]
    need(
        all(
            favorable["phase_saved"][p] - control["phase_saved"][p] == all_credit[p]
            for p in R["PHASES"]
        ),
        "credit counted twice",
    )
    return dict(
        first_deficit_ns=target,
        minimum_groups=len(picked),
        ordered_groups=picked,
        fewer_credit_ns=before,
        admitted_credit_ns=prefix,
        eligible_credit_ns=all_credit,
        free_previous_visit=favorable,
    )


def evaluate():
    need(
        sha(HERE / "advance-protocol.md") == METHOD and sha(PRIOR / "reads.json.gz") == READS,
        "inputs",
    )
    parent = T["verified"](PRIOR / "decision.json", PARENT)
    witness = json.loads(gzip.decompress((PRIOR / "reads.json.gz").read_bytes()))
    need(L["assess"](witness) == parent, "closed measured prices")
    spans, base = T["workload"]()
    words = witness["plan"]["ranks"]
    rows = L["regroup"](spans["P97"], base, words)
    eligible, counts = previous_visit(spans["P97"], words, rows)
    need((eligible, counts) == previous_visit(spans["P106"], words, rows), "forecast changed")
    proof = T["parse"](witness["stdout"].splitlines(), witness["plan"])
    out = {}
    signs = []
    for a in (1, 4):
        times = {i: t for i, _, _, t in proof["arms"][a - 1]}
        out[str(a)] = {}
        for tag, obs in spans.items():
            stat = per_arm(obs, times, eligible)
            original = parent["arms"][a - 1]["clocks"][tag]["next_router"]
            need(stat["first_deficit_ns"] == -original["first_margin"], "unmatched deadline")
            out[str(a)][tag] = stat
            signs.append(R["passes"](stat["free_previous_visit"]))
    return dict(
        method=METHOD,
        evidence="TRACE_DERIVED_OPTIMISTIC_BOUND",
        arms=out,
        policy_counts=counts,
        eligible_groups=len(eligible),
        m3="PARTIAL",
        m4="NOT_MET",
        decision="GO_FIXTURE_ONLY" if all(signs) else "NO_GO_ALL_FOUR_REQUIRED",
        any_joint=any(signs),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", type=Path)
    mode.add_argument("--new-output-dir", type=Path)
    a = cli.parse_args()
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        result = evaluate()
        if a.check:
            need(result == G["read"](a.check / "decision.json"), "published bound")
        else:
            T["save"](a.new_output_dir / ".pending", result)
            (a.new_output_dir / ".pending").rename(a.new_output_dir / "decision.json")
        print(result["decision"], result["eligible_groups"])
    except Exception as exc:
        if a.new_output_dir:
            T["save"](
                a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc))
            )
        raise
