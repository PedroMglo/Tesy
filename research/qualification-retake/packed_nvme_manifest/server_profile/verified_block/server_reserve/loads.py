"""Predict completed packed expert loads at drained cuts from C269 reservation generations."""

import argparse
import json
from pathlib import Path
from runpy import run_path


def predict(root, history, digest):
    source = (
        root
        / "research/qualification-retake/history_lookup/target_rollback/live_rollback/review.py"
    )
    review = run_path(str(source))
    r = review["R"]["reopen"](history, digest)
    review["need"](r["status"] == "GO_GREEDY_ROLLBACK_AND_CONTINUATION", "complete C269 family")
    cases = {}
    for mode in ("AR", "R0", "R1", "R2"):
        cap = review["F"]["capture"](history, r["unit"], mode)
        paths = (
            ["entry", *(f"keep-{j}" for j in range(1, 6))]
            if mode == "AR"
            else ["entry", "trim", "next-0", "next-1"]
        )
        rows = {}
        for label in paths:
            layers = review["pool"](cap / (label + ".pool"))
            rows[label] = {
                tier: sum(sum(layer["generation"]) for layer in layers[start:stop])
                for tier, start, stop in (("CPU", 0, 25), ("CUDA", 25, 36))
            }
        cases[mode] = rows
    contrasts = {}
    for k in range(3):
        pairs = {}
        for j, label in enumerate(("trim", "next-0", "next-1")):
            serial = cases["AR"][f"keep-{k + 1 + j}"]
            candidate = cases[f"R{k}"][label]
            gap = {tier: candidate[tier] - serial[tier] for tier in ("CPU", "CUDA")}
            pairs[label] = dict(
                serial=serial,
                block=candidate,
                delta=gap,
                delta_logical_bytes=sum(gap.values()) * 13219200,
            )
        contrasts[f"B{k}"] = pairs
    return dict(
        reference_sha256=digest,
        logical_bytes_per_load=13219200,
        predicted_cumulative_reservations=cases,
        equal_confirmed_depth=contrasts,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--history", required=True, type=Path)
    parser.add_argument("--new-output-dir", required=True, type=Path)
    a = parser.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    result = predict(
        a.repo, a.history, "9f384fe141eac5b8aa28128d778565870884f4f18c5105b4f7761c62548a3d86"
    )
    with (a.new_output_dir / "forecast.json").open("x") as out:
        json.dump(result, out, sort_keys=True, indent=2, allow_nan=False)
        out.write("\n")
