"""Find the smallest sets of unresolved read classes capable of changing the decision."""

import argparse
import json
import os
from itertools import combinations
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
D = run_path(HERE / "depths.py")
need, sha, save = (D[k] for k in ("need", "sha", "save"))
PIN = "c3efeedb791c1efaea793d1b2892f6ab85d17eff648a27466b136a6416877ad5"
PPM = 1_000_000


def evaluate(path):
    need(sha(path) == PIN, "registered price surface")
    old = json.loads(path.read_bytes())
    groups, per_arm, hits = D["inputs"]()
    X = D["replay"]()
    F = X["F"]
    basis, _, _ = F["freeze"]()
    ranges = old["rates_ppm"]
    unknown = [s for s, v in ranges.items() if v == [0, PPM]]
    need(len(unknown) == 4 and len(groups) == 6, "measured classes")

    def margin(rate):
        joint = []
        for tag, per_job in per_arm.items():
            cuts = {
                i: sum(v * rate[s] for s, v in weights.items()) // PPM
                for i, weights in per_job.items()
            }
            clk = F["clock"](F["adjusted"](basis["arms"][tag], cuts), hits, True, False, tag)
            joint.append(X["V"]["budget"](clk))
        return min(joint)

    resolutions = {}
    for side, endpoint in ((0, "low"), (1, "high")):
        known = {s: v[side] for s, v in ranges.items() if s not in unknown}

        def price(chosen, *, target=None, ppm=0, known=known):
            rate = known | {s: PPM if s in chosen else 0 for s in unknown}
            if target is not None:
                rate[target] = ppm
            return margin(rate)

        all_prices = []
        minimal = []
        for n in range(len(unknown) + 1):
            for selected in combinations(unknown, n):
                m = price(selected)
                all_prices.append([list(selected), m])
                if m >= 0 and not any(set(c) <= set(selected) for c in minimal):
                    minimal.append(list(selected))
        boundary = all_prices[0 if side == 0 else -1][1]
        need(boundary == old["margins_ns"]["favorable"][endpoint], "calibrated endpoint")
        single = {}
        for shape in unknown:
            others = set(unknown) - {shape}
            a, b = price(others), price(others, target=shape, ppm=PPM)
            if a >= 0 or b < 0:
                single[shape] = {"necessary_ppm": 0 if a >= 0 else None, "at_zero_margin_ns": a}
                continue
            lo, hi = 0, PPM
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if price(others, target=shape, ppm=mid) >= 0:
                    hi = mid
                else:
                    lo = mid
            left, right = (price(others, target=shape, ppm=x) for x in (lo, hi))
            need(left < 0 <= right, "adjacent thresholds")
            single[shape] = dict(
                necessary_ppm=hi,
                preceding_margin_ns=left,
                passing_margin_ns=right,
                at_zero_margin_ns=a,
            )
        resolutions[endpoint] = dict(
            subset_margins_ns=all_prices,
            minimal_passing_sets=minimal,
            single_with_other_unknowns_free=single,
        )
    return dict(
        evidence="DIAGNOSTIC_SELECTION_ONLY", projection=PIN, unknown=unknown, ranges=resolutions
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--projection", required=True, type=Path)
    output = p.add_mutually_exclusive_group(required=True)
    output.add_argument("--check", type=Path)
    output.add_argument("--new-output-dir", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        data = evaluate(a.projection)
        if a.check:
            need(data == json.loads(a.check.read_bytes()), "selection reproduction")
        else:
            save(a.new_output_dir / "thresholds.json", data)
        print(data["ranges"]["high"]["single_with_other_unknowns_free"])
    except Exception as error:
        if a.new_output_dir:
            save(
                a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(error))
            )
        raise
