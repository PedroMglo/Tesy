"""Bound counter increments during C110 phases without identifying a spawn epoch."""

import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
TERMINALS = {
    "D0": "8343243f506088714e3c16e83d834e82c85faa30878010a8837815f678c90c37",
    "D1": "a55554e02a4312ea81e49c9cdf31ff22e3fa115439d11692f9caf0c5b042b9ee",
}
SUPERVISOR = "67bf6c1cbd031f0e48fb3dc21b02ae81687935ca4db2a90090fecdf0ad6bf9c1"
PHASES = ("load", "context", "prefill", "teacher", "cleanup")


def need(ok, error):
    if not ok:
        raise ValueError(error)


def ns(seconds):
    value = Decimal(str(seconds)) * 10**9
    need(value.is_finite() and value >= 0 and int(value) == value, "not integer nanoseconds")
    return int(value)


def bounds(samples, total, begin, end, slack):
    """samples contain (earliest, latest, absolute counter). Return inclusive byte limits."""
    need(all(type(x) is int and x >= 0 for x in (total, begin, end, slack)), "bad window")
    need(begin < end, "empty phase")
    for i, (lo, hi, value) in enumerate(samples):
        need(0 <= lo <= hi and type(value) is int and value >= 0, "invalid counter sample")
        if i:
            need(samples[i - 1][1] <= lo and samples[i - 1][2] <= value, "order/regression")
    if not samples:
        return [0, total]
    first, last = samples[0][2], samples[-1][2]
    need(last - first <= total, "sampled increments exceed endpoint delta")

    # Between consecutive crossing times every comparison in the loop is constant.
    shifts = {0, slack}
    for lo, hi, _value in samples:
        for stamp in (lo, hi):
            for mark in (begin, end):
                cross = stamp - mark
                shifts.update(t for t in (cross - 1, cross, cross + 1) if 0 <= t <= slack)

    lower, upper = total, 0
    for shift in shifts:
        a, b = begin + shift, end + shift
        before = [value for _lo, hi, value in samples if hi < a]
        inside = [value for lo, hi, value in samples if a < lo and hi < b]
        after = [value for lo, _hi, value in samples if b < lo]
        floor = inside[-1] - inside[0] if inside else 0

        # Baseline counter B is not stored. B <= first and B + total >= last.
        # The full envelope is also available when some deltas have no sample.
        if before and after:
            ceiling = after[0] - before[-1]
        elif before:
            ceiling = first + total - before[-1]
        elif after:
            ceiling = after[0] - max(0, last - total)
        else:
            ceiling = total
        lower, upper = min(lower, floor), max(upper, min(total, ceiling))
    need(0 <= lower <= upper <= total, "inconsistent envelope")
    return [lower, upper]


def review(directory, arm):
    # First authenticate original terminal, stdout, gauges, input IDs/logits and clock order.
    original = run_path(str(HERE.parent / "cost/review.py"))["audit"](directory, TERMINALS[arm])
    terminal = json.loads((directory / "receipt.json").read_text(), parse_float=Decimal)
    need(
        original["arm"] == arm
        and original["arm_status"] == "PASS_IK_CPU_NUMERIC_ARM"
        and terminal["source_sha256"]["profile.py"] == SUPERVISOR
        and terminal["namespace"] == "nvme0n1",
        "unsupported producer or arm",
    )
    if arm == "D1":
        need(terminal["d0_sha256"] == TERMINALS["D0"], "D1 baseline")
    rows = [
        json.loads(line, parse_float=Decimal)
        for line in (directory / "raw/monitor.jsonl").read_text().splitlines()
    ]
    marks = terminal["phase_monotonic_ns"]
    origin = marks["load_begin"]
    span = marks["cleanup_end"] - origin
    duration = ns(terminal["elapsed_s"])
    slack = duration - span
    need(0 <= slack <= duration, "native span exceeds supervisor lifetime")
    stamps = [ns(row["elapsed_s"]) for row in rows]
    edges = list(zip([0, *stamps[:-1]], stamps, strict=True))
    need(stamps and all(lo < hi <= duration for lo, hi in edges), "sample timestamp ordering")

    def interval(samples, total):
        return {
            "observations": len(samples),
            "before_spawn_to_after_child_bytes": total,
            "phase_bytes": {
                phase: bounds(
                    samples,
                    total,
                    marks[phase + "_begin"] - origin,
                    marks[phase + "_end"] - origin,
                    slack,
                )
                for phase in PHASES
            },
        }

    streams = {}
    for dev in ("259:0", "8:0"):
        samples = [
            (lo, hi, row["io"][dev]["rbytes"])
            for (lo, hi), row in zip(edges, rows, strict=True)
            if "rbytes" in row["io"].get(dev, {})
        ]
        delta = terminal["io_by_device"].get(dev, {}).get("rbytes")
        if delta is None:
            need(not samples, "device disappeared in terminal io.stat")
            streams["scope_" + dev] = {"status": "NO_REPORTED_COUNTER", "observations": 0}
        else:
            streams["scope_" + dev] = interval(samples, delta)
    streams["namespace_nvme0n1"] = interval(
        [
            (lo, hi, row["disk_read_sectors"] * 512)
            for (lo, hi), row in zip(edges, rows, strict=True)
        ],
        terminal["namespace_read_bytes"],
    )
    return {
        "terminal_sha256": TERMINALS[arm],
        "monitor_sha256": original["runtime_monitor_sha256"],
        "first_native_mark_after_supervisor_start_ns": [0, slack],
        "native_first_to_last_ns": span,
        "supervisor_lifetime_ns": duration,
        "max_counter_sampling_window_ns": max(hi - lo for lo, hi in edges),
        "streams": streams,
    }


def compare(d0, d1):
    arms = {"D0": review(d0, "D0"), "D1": review(d1, "D1")}
    differences = {}
    for name in ("scope_259:0", "namespace_nvme0n1"):
        a, b = (arm["streams"][name]["phase_bytes"] for arm in arms.values())
        differences[name] = {
            phase: [a[phase][0] - b[phase][1], a[phase][1] - b[phase][0]] for phase in PHASES
        }
    return {
        "status": "REPRODUCED_C110_CPU_COUNTER_BOUNDS",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "arms": arms,
        "D0_minus_D1_bytes": differences,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("d0", "d1", "new-output"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    args.new_output.mkdir(mode=0o700, exist_ok=False)
    try:
        result = compare(args.d0, args.d1)
    except (OSError, ValueError, KeyError) as exc:
        result = {"status": "FAIL_PRESERVED", "error": str(exc)}
    pending = args.new_output / ".receipt.tmp"
    with pending.open("x") as sink:
        json.dump(result, sink, indent=2, sort_keys=True, allow_nan=False)
        sink.write("\n")
    pending.rename(args.new_output / "receipt.json")
    print(result["status"])
    raise SystemExit(int(result["status"] == "FAIL_PRESERVED"))
