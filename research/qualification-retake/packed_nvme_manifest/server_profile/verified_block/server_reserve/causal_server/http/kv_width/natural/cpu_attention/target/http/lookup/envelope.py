"""Bound combinations of priced verification groups on the same confirmed sequence."""

import argparse
from collections import defaultdict
from itertools import pairwise
from pathlib import Path
from runpy import run_path
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
HTTP = run_path(str(HERE / "review_http.py"))
AUDIT, R, G, need, save = (HTTP[k] for k in ("AUDIT", "R", "G", "need", "save"))
METHOD = "f36b54160b9cebdc85c1d9ed4c1285bb7ed70e232aa757d4e61b2d2259c93b42"
IO = run_path(str(HERE.parent / "prefill_io.py"))
RELOADS = "32f91f7a2a5922e558e597e60589f176d3951c981cd49bf83580bba7b59433ae"
SLOTS = "7d3e20f41f8e1c92add2e7bad358a1c61026950f2c145567f496c179d97c8063"


class Edge(NamedTuple):
    start: int
    end: int
    us: int
    early_us: int
    arm: str
    block: bool


def priced(mode, steps, marks, cut):
    actions = []
    for s in steps:
        start = s["at"] - 1
        end = start + s["emitted"]
        need(
            start == (actions[-1].end if actions else 0) and start < end < len(marks),
            "contiguous measured group",
        )
        delay = marks[end] - marks[start]
        early = 0 if cut is None else marks[min(max(cut, start), end)] - marks[start]
        need(0 <= early <= delay and delay > 0, "producer times within group")
        actions.append(Edge(start, end, delay, early, mode, bool(s["proposal"])))
    need(
        actions[-1].end == len(marks) - 1
        and sum(e.us for e in actions) == marks[-1] - marks[0]
        and (cut is None or sum(e.early_us for e in actions) == marks[cut] - marks[0]),
        "observed path conservation on both clocks",
    )
    return actions


def shortest(edges, n, reverse=False):
    by_origin = defaultdict(list)
    for e in edges:
        by_origin[e.end if reverse else e.start].append(e)
    origin = n if reverse else 0
    costs = {origin: 0}
    paths = {origin: ()}
    for pos in range(n, 0, -1) if reverse else range(n):
        for e in by_origin[pos]:
            dest = e.start if reverse else e.end
            candidate = costs[pos] + e.us
            if dest not in costs or candidate < costs[dest]:
                costs[dest] = candidate
                paths[dest] = ((e,) + paths[pos]) if reverse else (paths[pos] + (e,))
    for e in edges:
        left, right = (e.end, e.start) if reverse else (e.start, e.end)
        need(costs[right] <= costs[left] + e.us, "shortest path certificate")
    return paths


def clocks(path):
    return sum(e.early_us for e in path), sum(e.us for e in path)


def frontier(edges, n, cut):
    forward = shortest(edges, n)
    if cut is None:
        return [forward[n]]
    backward = shortest(edges, n, reverse=True)
    # A complete path crosses the first-final sample in exactly one group.
    # For a fixed crossing, the cheapest prefix and suffix jointly attain both minima.
    candidates = {}
    for e in edges:
        if e.start < cut <= e.end:
            path = forward[e.start] + (e,) + backward[e.end]
            candidates.setdefault(clocks(path), path)
    best_total = None
    result = []
    for (early, total), path in sorted(candidates.items()):
        if best_total is None or total < best_total:
            need(
                path[0].start == 0
                and path[-1].end == n
                and all(left.end == right.start for left, right in pairwise(path))
                and clocks(path) == (early, total),
                "feasible winning path",
            )
            best_total = total
            result.append(path)
    need(
        result and min(clocks(p)[1] for p in result) == clocks(forward[n])[1],
        "minimum decode retained",
    )
    return result


def fixture():
    n, cut = 4, 2
    baseline = [Edge(i, i + 1, 10, 10 if i < cut else 0, "SERIAL", False) for i in range(n)]
    choices = [
        Edge(0, 3, 21, 6, "FILTER", True),
        Edge(1, 4, 18, 4, "FIXED", True),
    ]
    edges = baseline + choices

    def enumerate_paths(node):
        if node == n:
            yield ()
            return
        for e in edges:
            if e.start == node:
                for tail in enumerate_paths(e.end):
                    yield (e,) + tail

    costs = {clocks(p) for p in enumerate_paths(0)}
    nondominated = sorted(
        k
        for k in costs
        if not any(other != k and other[0] <= k[0] and other[1] <= k[1] for other in costs)
    )
    got = [clocks(p) for p in frontier(edges, n, cut)]
    need(
        got == nondominated == [(6, 31), (14, 28)] and clocks(frontier(edges, n, None)[0])[1] == 28,
        "overlap, two incompatible winners and no identified text cut",
    )
    return dict(feasible_paths=len(list(enumerate_paths(0))), frontier_us=got)


def witness(path, baseline, marks, cut, nominal):
    early, total = clocks(path)
    decode = baseline["decode_s"] + (total - (marks[-1] - marks[0])) / 1e6
    rate = baseline["predicted"] / decode
    first = (
        None
        if cut is None
        else (baseline["first_final_s"] + (early - (marks[cut] - marks[0])) / 1e6)
    )
    return dict(
        producer_total_us=total,
        producer_until_first_final_us=None if cut is None else early,
        projected_decode_s=decode,
        projected_decode_tok_s=rate,
        projected_first_final_s=first,
        available_prefill_s_for_ten=(
            baseline["prefill_s"] + 10 - first if nominal and first is not None else None
        ),
        more_decode_s_to_six=(max(0.0, decode - baseline["predicted"] / 6) if nominal else None),
        joint_nominal=(
            decode <= baseline["predicted"] / 6 and first <= 10
            if nominal and first is not None
            else None
        ),
        groups=[dict(start=e.start, end=e.end, arm=e.arm, block=e.block) for e in path],
    )


def prefill_bounds(root, physical):
    ph = IO["PH"]
    backend = Path(HTTP["H"]["read"](root / "preset.json")["backend"])
    for location, files in ((G["REPO"], ph["SOURCE"]), (backend, ph["NATIVE"])):
        need(all(AUDIT["sha"](location / k) == v for k, v in files.items()), "phase clock sources")
    proof = HTTP["H"]["read"](root / "runtime-proof.json")
    need(
        proof["cuts"][-1]["monotonic_ns"]
        <= proof["signal"]["before_ns"]
        <= proof["signal"]["after_ns"]
        <= proof["verified_cleanup_ns"],
        "cleanup order",
    )
    previous = ph["phase_observations"](root)
    tight = ph["phase_observations"](root, verified_cleanup_ns=proof["verified_cleanup_ns"])
    compact = IO["compact"](previous, tight)
    reloads = G["read"](HERE.parent / "reload-result.json", RELOADS)
    slots = G["read"](HERE.parent / "slot-result.json", SLOTS)
    need(
        slots["prior_sha256"] == RELOADS
        and reloads["target_id_digests"]
        == [physical["arms"]["SERIAL"]["trajectories"][str(i)]["sampled_sha256"] for i in (1, 2)],
        "prior populations and same confirmed IDs",
    )
    return dict(
        read_bytes=compact["turns"]["T2"]["phases"]["native_prompt"]["counters"]["read_bytes"],
        common_epoch_width_ns=compact["tight_epoch_width_ns"],
        rate_Bps=IO["RATE"],
        matched_aligned_bytes=slots["aligned_reads_avoided_bytes"],
        all_reloads_aligned_bytes=reloads["population"]["total"]["aligned_bytes"],
        population_sha256=RELOADS,
        matched_sha256=SLOTS,
    )


def service_credit(w, volume):
    seconds = w["available_prefill_s_for_ten"]
    if seconds is None:
        return None
    room = (
        IO["budget"](seconds, volume["read_bytes"])["available_bytes_rounded_up"]
        if seconds > 0
        else 0
    )
    deficit = max(0, volume["read_bytes"]["min"] - room)
    return dict(
        maximum_service_bytes=room,
        minimum_bytes_removed=deficit,
        remaining_after_matched_signed_bytes=volume["read_bytes"]["min"]
        - room
        - volume["matched_aligned_bytes"],
        remaining_after_all_reloads_signed_bytes=volume["read_bytes"]["min"]
        - room
        - volume["all_reloads_aligned_bytes"],
    )


def study(a):
    commit, tree = G["tree"](G["REPO"])
    need(
        commit == a.commit and AUDIT["sha"](HERE / "envelope-protocol.md") == METHOD,
        "frozen replay",
    )
    physical = G["read"](HERE / "http-result.json", a.review_sha256)
    family = R["reopen"](a.family, physical["family_sha256"])
    need(
        family["commit"] == HTTP["COMMIT"]
        and family["status"] == physical["status"] == "GO_FOUR_NATURAL_DIAGNOSTICS",
        "closed natural family",
    )
    rules = G["read"](HERE / "result.json", HTTP["NATIVE"]["REVIEW"])
    plans = {
        m: G["read"](a.lookup_run / tag / "proposals.json", rules["raw_digests"][tag])
        for m, tag in (("FILTER", "ON"), ("FIXED", "OFF"))
    }
    control = fixture()
    volume = prefill_bounds(a.family / "SERIAL", physical)
    turns = {}
    for i, turn in enumerate(("T1", "T2"), 1):
        arms = {m: AUDIT["ticks"](a.family / m, i) for m in physical["arm_order"]}
        cuts = {row[1] for row in arms.values()}
        cut = cuts.pop() if len(cuts) == 1 else None
        reference = arms["SERIAL"][0]
        n = len(reference) - 1
        baseline = physical["arms"]["SERIAL"]["rows"][i - 1]
        need(
            n + 1 == baseline["predicted"]
            and all(len(k[0]) == n + 1 for k in arms.values())
            and len(
                {v["trajectories"][str(i)]["sampled_sha256"] for v in physical["arms"].values()}
            )
            == 1,
            "same output and denominator",
        )
        single = [dict(at=j + 1, emitted=1, proposal=[]) for j in range(n)]
        serial = priced("SERIAL", single, reference, cut)
        alternatives = []
        # Exact same action means identical draft as well as identical confirmed extent.
        duplicates = defaultdict(list)
        for m, plan in plans.items():
            for s, e in zip(plan[turn], priced(m, plan[turn], arms[m][0], cut), strict=True):
                alternatives.append(e)
                if e.block:
                    duplicates[(e.start, e.end, tuple(s["proposal"]))].append(e.us)
        spread = [max(v) - min(v) for v in duplicates.values() if len(v) > 1]
        all_ar = defaultdict(list)
        for e in serial + alternatives:
            if not e.block:
                all_ar[e.start].append(e.us)
        ar_spread = [max(v) - min(v) for v in all_ar.values() if len(v) > 1]
        results = {}
        for name, actions in (
            ("serial_reference", serial + [e for e in alternatives if e.block]),
            ("all_observed_serial", serial + alternatives),
        ):
            paths = frontier(actions, n, cut)
            winners = [witness(path, baseline, reference, cut, i == 2) for path in paths]
            if i == 2:
                for w in winners:
                    w["conditional_prefill_service"] = service_credit(w, volume)
            results[name] = dict(edges=len(actions), witnesses=winners)
        turns[turn] = dict(
            confirmed=n + 1,
            first_final_sample=None if cut is None else cut + 1,
            repeated_blocks=len(spread),
            range_block_price_differences_us=([min(spread), max(spread)] if spread else []),
            repeated_serial_sites=len(ar_spread),
            range_serial_price_differences_us=(
                [min(ar_spread), max(ar_spread)] if ar_spread else []
            ),
            scenarios=results,
        )
    return dict(
        status="TRACE_DERIVED_OBSERVED_GROUP_PRICES",
        commit=commit,
        tree=tree,
        method_sha256=METHOD,
        four_arm_review_sha256=a.review_sha256,
        family_sha256=physical["family_sha256"],
        new_model_starts=0,
        new_requests=0,
        serial_nominal_prefill=volume,
        fixture=control,
        turns=turns,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("family", "lookup-run", "new-output-dir"):
        parser.add_argument("--" + key, required=True, type=Path)
    for key in ("review-sha256", "commit"):
        parser.add_argument("--" + key, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    save(args.new_output_dir / "result.json", study(args))
