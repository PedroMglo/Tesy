"""Find the least call duration that satisfies the optimistic four-reader deadline windows."""

import argparse
import json
import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
L = run_path(HERE / "tile_lanes.py")
need, sha, save = (L[k] for k in ("need", "sha", "save"))
PARENT = "8e48debecdae3f47aba3f071828345afff1d0908cffc323e1c770610f99adf5b"


def minimum(jobs, floor, passing):
    # Moving the common deadline to the right only widens each job's allowable times.
    def certificate(t):
        return L["max_service"]([(i, d, a, t - tail) for i, d, a, tail, _ in jobs])

    left, right = floor, passing
    need(not certificate(left)["feasible"] and certificate(right)["feasible"], "registered bracket")
    while right - left > 1:
        mid = (left + right) // 2
        if certificate(mid)["feasible"]:
            right = mid
        else:
            left = mid
    last, first = certificate(left), certificate(right)
    need(last["deficit_worker_ns"] > 0 and first["feasible"], "adjacent certificates")
    return right, dict(
        preceding_ns=left, last_failure=last, first_feasible_ns=right, first_fit=first
    )


def evaluate():
    source = HERE / "evidence-lanes-20261128-r01/windows.json"
    need(sha(source) == PARENT, "prior registered limits")
    arms = {}

    def visit(tag, mode, jobs, floor, integral, credited):
        shortest, proof = minimum(jobs, floor, credited)
        arms.setdefault(tag, {})[mode] = dict(
            proof=proof,
            minimum_extra_over_floor_ns=shortest - floor,
            minimum_integral_first_ns=10**10 + shortest - integral,
            minimum_credited_first_ns=10**10 + shortest - credited,
            remaining_integral_ns=integral - shortest,
            remaining_credited_ns=credited - shortest,
        )

    prior = L["evaluate"](on_jobs=visit)
    need(prior == json.loads(source.read_bytes()), "unchanged decision and all earlier deadlines")
    return dict(
        prior=PARENT,
        arms=arms,
        evidence="FORMAL_CONDITIONAL_PREEMPTIBLE_LOWER_BOUND",
        use="DIAGNOSTIC_NO_CHANGE_TO_ADOPTION",
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
        out = evaluate()
        if a.check:
            need(json.loads(a.check.read_bytes()) == out, "threshold reproduction")
        else:
            save(a.new_output_dir / "thresholds.json", out)
        print(
            {
                tag: {m: v["remaining_credited_ns"] for m, v in x.items()}
                for tag, x in out["arms"].items()
            }
        )
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise
