"""How much uniform service reduction is needed to reach a conditional C163 ceiling?"""

import argparse
import json
import os
from pathlib import Path

from timing import C163, ROOT, Fixture, arm_report, inputs, lower_bound, need, replay, sha

PPM = 1_000_000


def first_crossing(score):
    """First ppm on the frozen discrete grid with nonnegative signed margin."""
    if score(0) >= 0:
        return 0
    if score(PPM) < 0:
        return None
    lo, hi = 0, PPM
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if score(mid) >= 0:
            hi = mid
        else:
            lo = mid
    need(score(lo) < 0 <= score(hi), "bracket does not straddle the gate")
    return hi


class Model:
    def __init__(self):
        self.calls = {}
        self.services = {}

    def capture(self, call, times, fixed, interior, jobs, identifiers, wait_cap):
        need(call not in self.calls, "duplicate callback window")
        self.calls[call] = (times, fixed, interior, jobs, identifiers, wait_cap)
        for key, (_, _, duration) in zip(identifiers, jobs, strict=True):
            need(key not in self.services, "duplicate retained logical identity")
            self.services[key] = duration

    def evaluate(self, mode, reduction_ppm=0, service=None):
        need(
            mode in ("fixed_nonwait", "observed_interiors_free") and 0 <= reduction_ppm <= PPM,
            "scenario outside freeze",
        )
        timespan = ceiling = worker_sum = 0
        for times, fixed, interior, jobs, keys, wait_cap in self.calls.values():
            changed = []
            for (r, d, measured), key in zip(jobs, keys, strict=True):
                value = measured if service is None else service[key]
                duration = value * (PPM - reduction_ppm) // PPM
                changed.append((r, d, duration))
                worker_sum += duration
            elapsed = times[-1] - times[0]
            delays = fixed if mode == "fixed_nonwait" else interior
            saving = elapsed + 1 - lower_bound(times, delays, changed)
            ceiling += min(saving, wait_cap) if mode == "fixed_nonwait" else saving
            timespan += elapsed
        return {
            "ceiling_us": ceiling,
            "signed_margin_us": (10 * ceiling - timespan) / 10,
            "retained_worker_us": worker_sum,
        }


def min_by_job(models):
    left, right = models
    need(set(left) == set(right), "different logical retained jobs between arms")
    return {key: min(value, right[key]) for key, value in left.items()}


def arm_margin(model, mode, best):
    cache = {}

    def at(p):
        if p not in cache:
            cache[p] = model.evaluate(mode, p)
        return cache[p]

    elapsed = sum(t[-1] - t[0] for t, *_ in model.calls.values())
    p = first_crossing(lambda n: 10 * at(n)["ceiling_us"] - elapsed)
    record = {"own_service": at(0), "first_grid_ppm": p}
    if p is not None:
        record.update(at_first_grid=at(p), at_previous_grid=at(p - 1) if p else None)
    measures = model.evaluate(mode, service=best)
    record["matched_best_from_either_arm"] = {
        **measures,
        "shortened_jobs": sum(best[k] < v for k, v in model.services.items()),
        "worker_us_removed_from_own": at(0)["retained_worker_us"] - measures["retained_worker_us"],
    }
    return p, record


def sensitivity(arms, mode):
    best = min_by_job([model.services for model in arms.values()])
    thresholds, records = {}, {}
    for arm, model in arms.items():
        thresholds[arm], records[arm] = arm_margin(model, mode, best)
    joint = max(thresholds.values()) if None not in thresholds.values() else None
    if joint is not None:
        for arm, model in arms.items():
            records[arm]["at_first_common_grid"] = model.evaluate(mode, joint)
    return {"first_common_grid_ppm": joint, "arms": records}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--raw-dir", type=Path, required=True)
    cli.add_argument("--evidence-dir", type=Path, default=ROOT / "results" / C163)
    cli.add_argument("--new-output-dir", type=Path, required=True)
    args = cli.parse_args()
    args.new_output_dir.mkdir()
    try:
        arms = {}
        for arm in ("c163-on-1", "c163-on-2"):
            initial, final, rows, routing, _ = inputs(args.raw_dir, args.evidence_dir, arm)
            replay(initial, final, rows, routing)
            for order in ("early", "late"):
                control, candidate = (Fixture(initial, order, protect) for protect in (False, True))
                for fixture in (control, candidate):
                    fixture.run([r for r in routing if r["call_id"] in (9, 10)])
                model = Model()
                old = arm_report(rows, routing, control, candidate, capture_windows=model.capture)
                need(
                    len(model.services) == 851
                    and model.evaluate("fixed_nonwait")["ceiling_us"]
                    == old["fixed_nonwait_saving_upper_us"]
                    and model.evaluate("observed_interiors_free")["ceiling_us"]
                    == old["observed_callback_interiors_free_saving_upper_us"],
                    "zero-service perturbation changed frozen C163 baseline",
                )
                if arm in arms:
                    need(
                        arms[arm].calls == model.calls, "FIFO scenarios have different constraints"
                    )
                arms[arm] = model
        result = {
            "freeze_sha256": sha(Path(__file__).with_name("margin_protocol.md")),
            "grid_ppm": 1,
            "scenarios": {
                m: sensitivity(arms, m) for m in ("fixed_nonwait", "observed_interiors_free")
            },
        }
        tmp = args.new_output_dir / ".receipt"
        with tmp.open("x") as out:
            json.dump(result, out, indent=2, allow_nan=False)
            out.write("\n")
        os.replace(tmp, args.new_output_dir / "receipt.json")
    except Exception as exc:
        (args.new_output_dir / "FAIL.txt").write_text(str(exc) + "\n")
        raise


if __name__ == "__main__":
    main()
