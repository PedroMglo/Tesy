"""Isolate which resident-hit delivery tier could pay for a different executor boundary."""

import argparse
import json
import os
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
A = run_path(HERE / "indivisible.py")
L, need, sha, save = (A[k] for k in ("L", "need", "sha", "save"))
BOUND = run_path(HERE / "lane_margin.py")
METHOD = "089663707286863a1e7477542ee04280d2d07f6d47fa122c457b123daa46fa9c"
PARENT = "a69ad9753e38f6d6f4917ed7276fefdb1e6b788d85b62a625db9d8f7b24bbeb9"


def demand():
    tx, effect = L["V"]["sources"]()
    root = L["X"]["ORIGINAL"] / "service.json.gz"
    need(sha(root) == L["V"]["SERVICE"], "original setter intervals")
    result = {}
    for tag, data in L["F"]["unpack"](root).items():
        tiers = {"CPU": Counter(), "CUDA": Counter()}
        for row, (_, source, _), (_, _, layer, slot, generation, expert, _) in zip(
            data["jobs"], effect, tx, strict=True
        ):
            need(row[0] == [layer, slot, generation, expert], "original routed consumer")
            if source is not None:
                t = tiers["CUDA" if layer >= 25 else "CPU"]
                t.update(hits=1, set_worker_ns=sum(row[j + 1] - row[j] for j in (7, 9, 11)))
        need(sum(v["hits"] for v in tiers.values()) == 674, "all hit deliveries")
        result[tag] = tiers
    return result


def evaluate():
    need(sha(HERE / "tiers-protocol.md") == METHOD, "preregistered tier ablation")
    ref = L["S"]["M"]["verified"](HERE / "evidence-indivisible-20261128-r01/service.json", PARENT)
    windows = {}

    def collect(tag, mode, jobs, floor, integral, credited):
        windows[tag, mode] = (jobs, floor, integral, credited)

    cases = {"cpu_direct": range(25), "cuda_direct": range(25, 36)}
    calc = A["evaluate"](extra_modes=cases, on_jobs=collect)
    for key in ("status", "method", "parent", "verdicts"):
        need(calc[key] == ref[key], "original verdict")
    output = {}
    for tag, rows in calc["arms"].items():
        out = {}
        for mode, line in rows.items():
            if mode in ("direct", "copied"):
                need(
                    line == ref["arms"][tag][mode]
                    and calc["groups"][f"{tag}-{mode}"] == ref["groups"][f"{tag}-{mode}"]
                    and calc["nontrivial_intervals"][f"{tag}-{mode}"]
                    == ref["nontrivial_intervals"][f"{tag}-{mode}"],
                    "original prices, indivisibility and deadlines",
                )
            jobs, floor, integral, credited = windows[tag, mode]
            fast = line["speeds"]["8000000000"]
            upper = fast["serial"]["phases_ns"]["call148"]
            lower = fast["pipeline"]["phases_ns"]["call148"]
            need(lower == floor <= upper, "series bounds")

            def flow(t, jobs=jobs):
                return L["max_service"]([(i, d, a, t - tail) for i, d, a, tail, _ in jobs])

            initial = flow(floor)
            if initial["feasible"]:
                shortest, proof = floor, dict(graph_floor_ns=floor, first_fit=initial)
            elif flow(upper)["feasible"]:
                shortest, proof = BOUND["minimum"](jobs, floor, upper)
            else:
                out[mode] = dict(status="NO_UPPER_BOUND", serial=flow(upper))
                continue
            clock = fast["pipeline"]
            pm = 10**10 + shortest - integral
            cm = 10**10 + shortest - credited
            decode_ok = clock["decode_ns"] <= 47 * 10**9 // 6
            status = (
                "NO_GO"
                if cm > 10**10 or not decode_ok
                else "GO_FIXTURE"
                if pm <= 10**10 and line["budgets"]["integral"]["status"] == "FOUR_LANE_WITNESS"
                else "HEADROOM_ONLY"
            )
            out[mode] = dict(
                status=status,
                minimum_call148_ns=shortest,
                minimum_integral_first_ns=pm,
                minimum_credited_first_ns=cm,
                remaining_integral_ns=integral - shortest,
                remaining_credited_ns=credited - shortest,
                decode_ns=clock["decode_ns"],
                threshold=proof,
                budgets=line["budgets"],
                speeds=line["speeds"],
                group_counts=calc["groups"][f"{tag}-{mode}"],
            )
        output[tag] = out
    outcomes = {}
    for mode in ("copied", *cases, "direct"):
        statuses = [row[mode]["status"] for row in output.values()]
        outcomes[mode] = (
            "NO_GO"
            if "NO_GO" in statuses
            else "INCONCLUSIVE_NO_UPPER_BOUND"
            if "NO_UPPER_BOUND" in statuses
            else "GO_FIXTURE"
            if statuses == ["GO_FIXTURE", "GO_FIXTURE"]
            else "HEADROOM_ONLY"
        )
    return dict(
        evidence="FORMAL_CONDITIONAL_ON_OBSERVED_SERVICE",
        method=METHOD,
        parent=PARENT,
        outcomes=outcomes,
        served_hits=demand(),
        arms=output,
        retained_search_intervals={
            k: v
            for k, v in calc["nontrivial_intervals"].items()
            if any(k.endswith(m) for m in cases)
        },
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
            need(r == json.loads(a.check.read_bytes()), "published tier ablation")
        else:
            save(a.new_output_dir / "tiers.json", r)
        print(r["outcomes"])
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise
