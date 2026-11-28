"""Certify non-preemptible service on the four readers within each routed consumer."""

import argparse
import json
import os
from collections import Counter, defaultdict
from functools import cache
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
L = run_path(HERE / "tile_lanes.py")
need, sha, save = (L[k] for k in ("need", "sha", "save"))
METHOD = "5ff06fb29ddab89971ff495af3af79f2638e4670865060ddb0e606aea91495e7"
PARENT = "8e48debecdae3f47aba3f071828345afff1d0908cffc323e1c770610f99adf5b"


def fit_budget(jobs, goal, limit):
    nodes = 0
    lanes = [0] * 4
    assignment = [0] * len(jobs)
    failed = set()

    def fit(idx):
        nonlocal nodes
        if nodes >= limit:
            return None
        nodes += 1
        if idx == len(jobs):
            return True
        state = (idx, tuple(sorted(lanes)))
        if state in failed:
            return False
        tried = set()
        for lane in sorted(range(4), key=lanes.__getitem__, reverse=True):
            before = lanes[lane]
            if before in tried or before + jobs[idx] > goal:
                continue
            tried.add(before)
            lanes[lane] += jobs[idx]
            assignment[idx] = lane
            found = fit(idx + 1)
            if found is True:
                return True
            lanes[lane] = before
            if found is None:
                return None
        failed.add(state)
        return False

    feasible = fit(0)
    return feasible, max(lanes), assignment, nodes


def pack(prices, limit=20_000):
    need(
        all(isinstance(v, int) and v >= 0 for v in prices) and limit >= 0,
        "nonnegative integral costs and budget",
    )
    jobs = sorted((p for p in prices if p), reverse=True)
    lower = (sum(jobs) + 3) // 4
    for k in range(1, len(jobs) + 1):
        occupants = (k + 3) // 4
        lower = max(lower, sum(jobs[k - occupants : k]))
    loads = [0] * 4
    witness = []
    for price in jobs:
        lane = min(range(4), key=loads.__getitem__)
        loads[lane] += price
        witness.append(lane)
    upper = max(loads)
    nodes = 0
    while lower < upper and nodes < limit:
        goal = (lower + upper) // 2
        feasible, cost, assignment, visits = fit_budget(jobs, goal, limit - nodes)
        nodes += visits
        if feasible is None:
            break
        if feasible:
            upper = cost
            witness = assignment
        else:
            lower = goal + 1
    verified = [0] * 4
    for price, lane in zip(jobs, witness, strict=True):
        verified[lane] += price
    need(lower <= max(verified) == upper and nodes <= limit, "assignment and certified interval")
    return lower, upper, nodes, witness


def evaluate(*, extra_modes=None, on_jobs=None):
    need(sha(HERE / "indivisible-protocol.md") == METHOD, "registered atomic service")
    old = L["S"]["M"]["verified"](HERE / "evidence-lanes-20261128-r01/windows.json", PARENT)
    need(L["evaluate"]() == old, "all preemptible controls")
    counts = defaultdict(Counter)
    detail = defaultdict(list)
    solve = cache(pack)

    def price(tag, mode, call, tile, layer, durations):
        key = f"{tag}-{mode}"
        low, high, n, assignment = solve(tuple(sorted(durations, reverse=True)))
        original = max(max(durations), (sum(durations) + 3) // 4)
        counts[key].update(
            groups=1,
            exact=int(low == high),
            unresolved=int(low < high),
            stronger=int(low > original),
            sum_added_site_ns=low - original,
        )
        if low != original or low != high:
            detail[key].append(
                [call, tile, layer, len(durations), original, low, high, n, L["digest"](assignment)]
            )
        return low

    calculus = L["evaluate"](site_floor=price, extra_modes=extra_modes, on_jobs=on_jobs)
    verdicts = {}
    for mode in ("copied", "direct"):
        signs = []
        for arm in calculus["arms"].values():
            line = arm[mode]
            clock = line["speeds"]["8000000000"]["pipeline"]
            signs.append(
                clock["decode_ns"] <= 47 * 10**9 // 6
                and line["budgets"]["credited"]["status"]
                not in ("GRAPH_INFEASIBLE", "IMPOSSIBLE_EVEN_PREEMPTIBLE")
            )
        verdicts[mode] = "HEADROOM_ONLY" if all(signs) else "NO_GO"
    status = (
        "NO_GO_INDIVISIBLE_PROFILE"
        if verdicts["direct"] == "NO_GO"
        else "NO_GO_COPIED_DIRECT_INCONCLUSIVE"
        if verdicts["copied"] == "NO_GO"
        else calculus["status"]
    )
    return dict(
        status=status,
        method=METHOD,
        parent=PARENT,
        verdicts=verdicts,
        evidence="FORMAL_CONDITIONAL_ON_CALIBRATED_SERVICE",
        arms=calculus["arms"],
        groups=counts,
        nontrivial_intervals=detail,
        max_nodes_per_group=20000,
        model_forwards=0,
        http_requests=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    dest = p.add_mutually_exclusive_group(required=True)
    dest.add_argument("--new-output-dir", type=Path)
    dest.add_argument("--check", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        r = evaluate()
        if a.check:
            need(r == json.loads(a.check.read_bytes()), "published indivisible service")
        else:
            save(a.new_output_dir / "service.json", r)
        print(r["status"], r["verdicts"])
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise
