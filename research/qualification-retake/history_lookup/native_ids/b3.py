"""Screen causal N=2/M=2 against the newly authenticated natural trajectory."""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULE = HERE.parent / "causal_pair/screen.py"
RULE_SHA = "797746256c463790abc44463e56948636fa63b03f9d0e710daa29203f8a9846e"
HISTORICAL = "cb191e31c2e3ee547a01228065a3c4253bdb312dd1e561d361f75365f065356a"
INPUT_SHA = "cf7e9b19362c5aeaf5e54e2185048acac09ec55459fb4a6fc262ec434f037425"
INPUT_FILE = "986e254f8424298f6b442a4e7351c982381e31f81423486ed21069bae53b25c7"


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pinned(path, expected):
    data = path.read_bytes()
    check(sha(data) == expected, "digest mismatch: " + path.name)
    return data


def limits(row, decode_s, full=False):
    steps = row["outputs"]
    ordinary = row["ordinary"]
    checks = row["proposals"]
    check(
        steps > 0 and ordinary + checks == row["calls"] and ordinary + checks <= steps,
        "incoherent call count",
    )
    # This is the historical 15% reduction screen, not an end-to-end throughput claim.
    allow15 = 0.85 * steps - ordinary
    budget = dict(
        maximum_ratio_b3_per_ar_for_15pct_less_decode=allow15 / checks if checks else None,
        free_overhead_b3_equal_to_ar_reaches_15pct=row["calls"] <= 0.85 * steps,
    )
    if full:
        check(steps == 46 and math.isfinite(decode_s) and decode_s > 0, "full generation clock")
        ar_s = decode_s / steps
        total_ar_equivalents = (47 / 6) / ar_s
        budget.update(
            historical_mean_ar_seconds=ar_s,
            historical_6tps_target_seconds=47 / 6,
            maximum_ratio_b3_per_ar_for_6tps=(total_ar_equivalents - ordinary) / checks
            if checks
            else None,
            free_overhead_b3_equal_to_ar_reaches_6tps=row["calls"] <= total_ar_equivalents,
            coordination_budget_seconds_6tps_if_b3_costs_one_ar=47 / 6 - row["calls"] * ar_s,
        )
    return budget


def run(args):
    spec = importlib.util.spec_from_file_location("c281_causal_rule", RULE)
    pinned(RULE, RULE_SHA)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    hist = json.loads(pinned(args.historical / "receipt.json", HISTORICAL))
    verified = json.loads(pinned(args.verified / "receipt.json", args.verified_sha256))
    check(
        verified["status"] == "PASS_TWO_NATURAL_SAMPLED_TRAJECTORIES",
        "trajectory verification failed",
    )
    pinned(args.capture / "receipt.json", verified["capture_receipt_sha256"])
    check(verified["historical_receipt_sha256"] == HISTORICAL, "verification control mismatch")
    turns = verified["turns"]
    check(len(turns) == 2, "verified turn count")
    targets = []
    for row, label, count in zip(turns, ("T1", "T2"), (78, 47), strict=True):
        check(row["label"] == label and row["count"] == count, "turn schema")
        data = pinned(args.verified / (label + "-sampled.i32"), row["sampled_ids_sha256"])
        check(len(data) == 4 * count, "sampled i32 count")
        values = struct.unpack(f"<{count}i", data)
        check(all(0 <= v < 201088 for v in values), "native vocabulary bounds")
        targets.append(values)
    target = targets[1]
    prompt = json.loads(pinned(args.capture / "raw/T2-input.json", INPUT_FILE))["official_ids"]
    check(
        len(prompt) == 2197
        and sha(struct.pack("<2197i", *prompt)) == INPUT_SHA
        and turns[1]["official_ids_sha256"] == INPUT_SHA,
        "official prompt",
    )
    sealed = hist["rows"][1]
    check(
        sealed["predicted_n"] == sealed["completion_n"] == 47 and sealed["input_n"] == 2197,
        "historical time denominator",
    )
    rows = []
    for stop in (33, 47):
        row = module.replay(prompt, target[:stop], 2, 2)
        check(row["outputs"] == stop - 1, "anchor accounting")
        rows.append(dict(**row, **limits(row, sealed["decode_s"], stop == 47)))
    return dict(
        status="REPRODUCED_NEW_NATURAL_B3_CALL_SCREEN",
        rule_sha256=RULE_SHA,
        verified_sha256=args.verified_sha256,
        historical_sha256=HISTORICAL,
        prompt_i32_sha256=INPUT_SHA,
        sampled_i32_sha256=turns[1]["sampled_ids_sha256"],
        n=2,
        m=2,
        first_id_from_prefill=1,
        windows=rows,
        historical_first_final_minus_whole_decode_s=sealed["first_final_s"] - sealed["decode_s"],
        historical_prefill_s=sealed["prefill_s"],
        historical_decode_s=sealed["decode_s"],
        historical_first_final_s=sealed["first_final_s"],
        candidate_verification_cost="NOT_MEASURED",
        historical_sampled_ids_identity="UNKNOWN",
        source_sha256=sha(Path(__file__).read_bytes()),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("historical", "verified", "capture", "new-output-dir"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--verified-sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir(mode=0o700)
    try:
        receipt = run(args)
    except Exception as exc:
        receipt = dict(status="FAIL_PRESERVED", failure=f"{type(exc).__name__}: {exc}")
    with (args.new_output_dir / "receipt.json").open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(receipt["status"])
    return int(receipt["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
