"""Compact two independent runs; retain both request clocks and the disjoint phase credits."""

import argparse
import hashlib
import json
from pathlib import Path


def compact(first, second):
    data = first.read_bytes()
    if data != second.read_bytes():
        raise ValueError("independent receipts differ")
    r = json.loads(data)
    if r["status"] != "REPRODUCED_UNION_AT_FIXED_AR_PRICES":
        raise ValueError("source run not complete")
    out = {
        "status": r["status"],
        "raw_sha256": hashlib.sha256(data).hexdigest(),
        "code_sha256": r["code_sha256"],
        "sources": r["sources"],
        "provenance": r["provenance"],
    }
    for tag in ("P97", "P106"):
        src = r[tag]
        obj = {k: v for k, v in src.items() if k != "banks"}
        obj["banks"] = {}
        for name in ("lru", "prefill"):
            b = src["banks"][name]
            prices = {}
            for model, vals in b["prices"].items():
                if model == "drained_retained_origins":
                    if vals != b["prices"]["drained"]:
                        raise ValueError(
                            "different retained-origin sensitivity; publish separately"
                        )
                    continue
                prices[model] = {
                    suffix: {
                        scale: [
                            x[k]
                            for k in (
                                "prefill_ns",
                                "first_final_ns",
                                "decode_ns",
                                "first_new_cost_budget_ns",
                                "decode_new_cost_budget_ns",
                                "uniform_extra_per_attempt_ns",
                                "joint",
                            )
                        ]
                        for scale, x in mix.items()
                    }
                    for suffix, mix in vals.items()
                }
            obj["banks"][name] = {
                "prices": prices,
                "counts": b["counts"],
                "drained_phases": b["influence"]["drained"],
                "wave_table_sha256": b["wave_table_sha256"],
                "drained_prices_unchanged_when_excluding_free_origins": True,
            }
        out[tag] = obj
    out["price_columns"] = [
        "prefill_ns",
        "first_final_ns",
        "decode_ns",
        "first_new_cost_budget_ns",
        "decode_new_cost_budget_ns",
        "uniform_extra_per_attempt_ns",
        "joint",
    ]
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for k in ("first", "second", "new-output"):
        ap.add_argument("--" + k, type=Path, required=True)
    a = ap.parse_args()
    summary = compact(a.first, a.second)
    with a.new_output.open("x") as f:
        json.dump(summary, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
