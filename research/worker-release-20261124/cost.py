"""Reproduce C318 costs and conditional decode thresholds from locked receipts."""

import argparse
import json
import math
from pathlib import Path
from statistics import mean

from audit import require, source

PREFILL, DECODE, TOTAL = "prefill153_s", "decode32_s", "total_s"
METRICS = ("prefix_s", PREFILL, DECODE, TOTAL)


def gains(pairs, discount=0):
    return [
        {k: 100 * (1 - (b[k] - discount * b[DECODE] * (k in (TOTAL, DECODE))) / a[k])
         for k in METRICS}
        for a, b in pairs
    ]


def verify_clocks(row):
    parts = [row["decode_forward_s"], row["stage_cleanup_s"]]
    require(all(math.isfinite(x) and x >= 0 for x in parts)
            and math.isclose(sum(parts), row["metrics"][DECODE], rel_tol=0, abs_tol=1e-8),
            "decode receipt excludes cleanup or has unknown forward/cleanup phase")


def case_cost(case, published, numerics, other_total):
    arithmetic = source.historical_cost(case, published)
    arms = []
    for arm, role in enumerate(("R0", "learned", "learned", "R0"), 1):
        row = source.archived(f"{source.C318}/c318-{case}-{arm}-{role}-analysis.json")
        verify_clocks(row)
        require(row["full33_logits_sha256"] == numerics, "historical logits receipt mismatch")
        arms.append({"arm": arm, "role": role, **row["metrics"],
                     "decode_forward_s": row["decode_forward_s"],
                     "stage_cleanup_s": row["stage_cleanup_s"]})
    a, b, other_b, other_a = arms
    pairs = [(a, b), (other_a, other_b)]
    historical = gains(pairs)
    median = {k: mean(x[k] for x in historical) for k in METRICS}
    for k in METRICS:
        require(math.isclose(median[k], published["median_paired_gain_percent"][k],
                             rel_tol=0, abs_tol=1e-8), "historical medians disagree")
    checks = {
        "global_total": median[TOTAL] >= 8 and all(row[TOTAL] > 0 for row in historical),
        "global_decode": (median[DECODE] >= 15 and median[TOTAL] > 0
                          and all(row[DECODE] > 0 for row in historical)),
        "other_case_protected": other_total >= -5,
    }
    for target, protected in ((PREFILL, DECODE), (DECODE, PREFILL)):
        checks[f"phase_{target}"] = (median[target] >= 10 and median[TOTAL] > 0
                                     and all(row[target] > 0 for row in historical)
                                     and median[protected] >= -5
                                     and checks["other_case_protected"])
    # The unique decode-only discount needed in both B arms to reach the
    # composition gate. A strict sign constraint still applies at the infimum.
    decode_phase = max(
        source.decode_discount(pairs, DECODE, 0.10),
        source.decode_discount(pairs, TOTAL, 0),
        *(1 - a[DECODE] / b[DECODE] for a, b in pairs),
    )
    return {
        "trace_off_arms_ABBA": arms,
        "pair_gain_percent_AB_BA": historical,
        "median_paired_gain_percent": median,
        "historical_gate_checks": checks,
        "fixed_prefill_protects_decode_phase": median[PREFILL] >= -5,
        "decode_phase_infimum_pct_with_other_case_fixed": (
            100 * decode_phase if median[PREFILL] >= -5 and other_total >= -5 else None
        ),
        "global_infima_pct_with_other_case_fixed": (
            arithmetic["conditional_local_gate_infima_pct"] if other_total >= -5 else None
        ),
        "seconds_per_candidate_at_cheaper_global_gate_AB_BA": (
            arithmetic["decode_seconds_to_remove_AB_BA_at_cheapest_gate"]
            if other_total >= -5 else None
        ),
        "maximum_uniform_decode_slowdown_pct_if_protected_case": (
            100 * (0.05 + median[TOTAL] / 100) / mean(b[DECODE] / a[TOTAL] for a, b in pairs)
        ),
    }


def report():
    paired = source.archived(f"{source.C318}/paired-cost-analysis.json")
    result = {}
    for case, other in (source.CASES, source.CASES[::-1]):
        history = paired["cases"]
        hashes = paired["full33_logits_sha256"][case]
        require(len(hashes) == 4 and len(set(hashes)) == 1, "historical full33 equality missing")
        result[case] = case_cost(case, history[case], hashes[0],
                                 history[other]["median_paired_gain_percent"][TOTAL])
    require(paired["status"] == "NO_GO_REAL_STAGING_INTEGRATED_COST"
            and not paired["global_qualified_cases"] and not paired["phase_survivor"]
            and all(not any(ok for name, ok in r["historical_gate_checks"].items()
                            if name != "other_case_protected") for r in result.values()),
            "historical evaluator disagrees")
    return {"classification": "REPRODUZIDO_MODEL_FREE",
            "historical_evaluator_status": paired["status"], "cases": result}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    value = report()
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(value, out, indent=2, allow_nan=False)
        out.write("\n")
