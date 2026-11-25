"""Conditional trade-offs on the original C281 client clock, with variable decode rate."""

import argparse
import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAPS = "4a9f2f7c7985120323d5075521e7d89b67c9c08ec182baece3bcf499bd96340b"
CUTS = "de7e2eb8b29332ea70cb5013c55e2cd8b23077c537c36a52f119089716ce9801"
METHOD = "326fcc0a09a958c9c68b299bb614750b4e35f6693072feff8537f2c7e5eb7210"
RATE = 4_500_000_000
PAYLOAD = 13_219_200


def pinned_bytes(path, digest):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(path.name)
    return data


def crossing(seconds, loads, gaps, count):
    io = loads * PAYLOAD / RATE
    if min(seconds, loads, gaps, count) <= 0:
        raise ValueError("nonpositive input")
    envelope = seconds + count / 6
    available = envelope - io - gaps
    dec = count / available if available > 0 else None
    both = (gaps + count / 6) / (envelope - io) if envelope > io else None
    all_three = (io + gaps + count / 6) / envelope
    for x, y in (
        (io + gaps + count / dec if dec else None, envelope),
        (io + (gaps + count / 6) / both if both else None, envelope),
        ((io + gaps + count / 6) / all_three, envelope),
    ):
        if x is not None and not math.isclose(x, y, rel_tol=1e-12):
            raise ValueError("budget does not close")
    return dict(
        prefill_reads=loads,
        prefill_payload_s=io,
        prefill_gap_s=gaps,
        envelope_s=envelope,
        excess_s_at_6=io + gaps - seconds,
        min_decode_rate_holding_prefill_prices=dec,
        min_common_speed_factor_decode_and_gaps=both,
        min_common_speed_factor_decode_and_gaps_and_prefill_bandwidth=all_three,
    )


def run():
    pinned_bytes(HERE / "tradeoff-protocol.md", METHOD)
    measured = json.loads(pinned_bytes(HERE / "receipt.json", GAPS))["arms"]["part-40"]
    optimum = json.loads(pinned_bytes(HERE.parent / "cuts-receipt.json", CUTS))
    if measured["journal_sha256"] != optimum["journal_sha256"]:
        raise ValueError("different T2")
    result = {}
    for count, row in measured["denominators"].items():
        result[count] = case = {}
        for name, arm in optimum["arms"].items():
            (best,) = (c for c in arm["cuts"] if c["released_after_tile_of_148"] == [1, 2, 3, 4])
            gap = measured["total"]["drained_ns"] / 1e9
            case[name] = crossing(row["budget_ns_ceil"] / 1e9, best["total"], gap, int(count))
        victims = case["victims"]
        expected_excess = victims["prefill_gap_s"] - row["max_gap_ns_before_gaps"] / 1e9
        if abs(victims["excess_s_at_6"] - expected_excess) > 1e-9:
            raise ValueError("fixed 6 tok/s cross-check")
        for key in (
            "prefill_reads",
            "min_decode_rate_holding_prefill_prices",
            "min_common_speed_factor_decode_and_gaps",
            "min_common_speed_factor_decode_and_gaps_and_prefill_bandwidth",
        ):
            if not case["empty"][key] >= case["published"][key] >= victims[key]:
                raise ValueError("bank ordering")
    return dict(
        status="REPRODUCED_CONDITIONAL_TRADEOFF",
        method_sha256=METHOD,
        program_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        gap_receipt_sha256=GAPS,
        cuts_receipt_sha256=CUTS,
        cases=result,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    out = parser.parse_args().new_output_dir
    out.mkdir(mode=0o700)
    try:
        result = run()
    except (KeyError, OSError, ValueError) as exc:
        result = dict(status="FAIL_PRESERVED", reason=str(exc))
    tmp = out / "report.tmp"
    with tmp.open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    tmp.rename(out / "receipt.json")
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
