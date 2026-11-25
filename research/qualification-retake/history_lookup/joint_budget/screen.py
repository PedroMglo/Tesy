"""Combine measured phase bounds and causal call counts in a conditional product budget."""

import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path

PHASE = "0a37abed553a3d36e00df88a22109f2c505be39892e0c3862f35c8e90bbe680a"
CALLS = "649bc3fe8f9e6469ab5cf7519ded4c5cb7d684cf36c792ca2a4b5eba018a7cbf"


def read(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("input receipt mismatch")
    return json.loads(data)


def budget(turn, calls, bandwidth, volume):
    # Native durations and client first final observed on the same OFF request.
    n = turn["predicted_n"]
    prompt, decode, first = (
        Fraction(turn[key], 10**9) for key in ("prompt_ns", "decode_ns", "first_final_ns")
    )
    # Discount *all* elapsed native decode from first final, even its tail after first final.
    time_for_both = 10 + prompt + decode - first
    ar = decode / calls["outputs"]
    cost_reads = Fraction(volume, bandwidth)
    max_decode = min(Fraction(n, 6), time_for_both - cost_reads)
    ordinary, proposals = calls["ordinary"], calls["proposals"]
    decode_equal = (ordinary + proposals) * ar
    headroom = max_decode - decode_equal
    available_for_prefill = time_for_both - decode_equal
    return {
        "process_read_bytes_assumed_mandatory": volume,
        "prefill_service_only_s": float(cost_reads),
        "largest_decode_s_satisfying_both": float(max_decode),
        "necessary_tok_per_s_if_no_other_costs": float(n / max_decode),
        "largest_b3_over_ar_if_no_other_costs": float((max_decode / ar - ordinary) / proposals),
        "decode_s_if_b3_equals_ar": float(decode_equal),
        "other_exposed_cost_budget_s_if_b3_equals_ar": float(headroom),
        "prefill_s_available_if_b3_equals_ar": float(available_for_prefill),
        "maximum_read_bytes_if_b3_equals_ar": int(available_for_prefill * bandwidth),
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for arg in ("phases", "b3", "new-output-dir"):
        ap.add_argument("--" + arg, type=Path, required=True)
    args = ap.parse_args()
    phase, b3 = read(args.phases, PHASE), read(args.b3, CALLS)
    nominal = phase["turns"][1]
    full = b3["windows"][-1]
    if not (
        nominal["predicted_n"] == full["outputs"] + 1 == 47
        and full["proposals"]
        and nominal["prompt_n"] == 153
        and nominal["cache_n"] == 2044
    ):
        raise ValueError("different denominators")
    bandwidth = phase["conditional"]["assumed_Bps"]
    reads = nominal["phases"]["native_prompt"]["counters"]["read_bytes"]
    result = {
        "status": "INCONCLUSIVE_JOINT_COST_AND_BYTES_ATTRIBUTION",
        "phase_sha256": PHASE,
        "calls_sha256": CALLS,
        "assumed_Bps": bandwidth,
        "scenarios": {
            edge: budget(nominal, full, bandwidth, volume)
            for edge, volume in reads.items()
            if volume is not None
        },
        "scope": "OFF clocks and aggregate I/O; new debug ID trajectory; zero extra exposed costs",
    }
    args.new_output_dir.mkdir(mode=0o700)
    with (args.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
