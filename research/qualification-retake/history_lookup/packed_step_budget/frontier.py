"""Compose the packed first-final cut with paid target verification and prefill reads."""

import argparse
import hashlib
import json
from pathlib import Path

ORDERS = {
    "ROP": "1cef0f0e32e21f3304812479f5eb34e7f166423b85a96832210578c4dbf9aafb",
    "POR": "1f1f819076b6ea26ba3a5a04b064cae662fd11f8a0f93ee94abb3f2efff286d4",
}
BAND = "11cfef208de11890c1da9210029b00526dbbbe1b36085536de0fed2c5b9ccc7a"
OBSERVED = (
    "igpu_resident_rank/request_budget/device/pack_native/natural_trace/release/"
    "lookahead2/decode/all_prefill/bandwidth/receipt.json"
)


def checked(path, digest):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("changed input " + path.name)
    return json.loads(data)


def frontier(qual):
    observations = checked(qual / OBSERVED, BAND)
    phases = {key: observations[key]["observed"]["prefill"] for key in ("P97", "P106")}
    size, calls = phases["P97"]["returned_bytes"], phases["P97"]["reads"]
    if any(
        p["requested_bytes"] != p["returned_bytes"]
        or p["returned_bytes"] != size
        or p["reads"] != calls
        or p["distinct_workers"] != 4
        for p in phases.values()
    ):
        raise ValueError("different baseline service")
    stride, remainder = divmod(size, calls)
    if remainder:
        raise ValueError("unaligned transaction shape")
    orders = {}
    for order, digest in ORDERS.items():
        data = checked(
            qual / "history_lookup/packed_step_budget" / (order.lower() + ".json"), digest
        )
        windows = {}
        for marker, window in data["windows"].items():
            counts = window["before_counts"]
            if (
                counts != {"ar": 23, "anchor": 10, "skip": 11}
                or window["first_final_sample_one_based"] != 45
            ):
                raise ValueError("changed causal cut")
            # Upper budget for prefill plus all verification/coordination before the first final.
            joint = 10**10 + data["prefill_ns"] - window["first_final_if_all_eligible_free_ns"]
            # Decimal 4.5 GB/s == 9 bytes per 2 ns. Never round the allowed read count upwards.
            scenarios = {}
            for mean_ms in (0, 100, 150, 200, 250, 300):
                available = joint - counts["anchor"] * mean_ms * 10**6
                max_reads = min(calls, max(0, (available * 9) // (2 * stride)))
                scenarios[str(mean_ms)] = dict(
                    max_prefill_ns=available, min_reads_moved=calls - max_reads
                )
            windows[marker] = dict(
                first_final_sample=45,
                prefinal_verifications=counts["anchor"],
                full_verifications=11,
                budget_prefill_plus_ten_ns=joint,
                maximum_mean_prefinal_verification_ms_at_4p5=(joint - size * 2 / 9) / 1e7,
                maximum_mean_full_verification_ms_at_six=window["average_verify_six_s"] * 1000,
                min_reduction_if_observed_read_union_retained_ns={
                    k: max(0, p["union_ns"] - joint) for k, p in phases.items()
                },
                prefinal_mean_ms_scenarios=scenarios,
            )
        orders[order] = windows
    return dict(
        status="CONDITIONAL_COMBINED_FRONTIER",
        product_orders_sha256=ORDERS,
        read_receipt_sha256=BAND,
        observed_prefill={
            k: {
                n: p[n]
                for n in (
                    "requested_bytes",
                    "returned_bytes",
                    "payload_bytes",
                    "reads",
                    "union_ns",
                    "span_ns",
                    "worker_ns",
                )
            }
            for k, p in phases.items()
        },
        returned_bytes_per_transaction=stride,
        assumed_returned_Bps=4500000000,
        arms=orders,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--qualification-root", type=Path, default=Path("research/qualification-retake")
    )
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    result = frontier(args.qualification_root)
    with (args.new_output_dir / "result.json").open("x") as f:
        f.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(result["status"])
