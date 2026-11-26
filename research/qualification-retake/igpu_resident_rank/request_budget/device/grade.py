"""Price one authenticated P request on two producer clocks and one device sampler."""

import hashlib
import json
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[2]
STEP = QUAL / "history_lookup/packed_step_budget/screen.py"
PAST = HERE.parent / "receipt.json"
CLOCKS = ("sample", "feed_terminal_sample")
HEADER = "lo_ns\thi_ns\trbytes\trios\tread_sectors\tinflight"
MARGIN = 2000
MAX_GAP = 500_000_000


def check(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def pin(path, expected):
    check(sha(path) == expected, f"identity {path.name}")
    return path


@dataclass(frozen=True)
class Sample:
    lo: int
    hi: int
    rbytes: int
    rios: int
    sectors: int
    inflight: int


def read_trace(path):
    check(path.is_file() and not path.is_symlink() and path.stat().st_size <= 2 << 20, "trace size")
    with path.open(encoding="ascii", newline="") as stream:
        check(stream.readline().rstrip("\n") == HEADER, "sampler header")
        rows = []
        for line in stream:
            cols = line.rstrip("\n").split("\t")
            check(len(cols) == 6 and len(rows) < 6650, "sampler record width/count")
            row = Sample(*map(int, cols))
            check(
                0 < row.lo <= row.hi
                and (not rows or rows[-1].hi < row.lo)
                and (row.rbytes == row.rios == -1 or min(row.rbytes, row.rios) >= 0)
                and min(row.sectors, row.inflight) >= 0,
                "sampler clock order or invalid field",
            )
            rows.append(row)
    return rows


def counter_bounds(relevant, inside, outer, fields, factor=1):
    def valid(segment):
        return all(getattr(r, f) >= 0 for r in segment for f in fields) and all(
            getattr(a, f) <= getattr(b, f) for a, b in pairwise(segment) for f in fields
        )

    valid_inner = valid(relevant)
    valid_outer = bool(outer) and valid(outer)
    return {
        "observed_monotone_in_window": valid_inner,
        "lower": (
            factor * (getattr(inside[-1], fields[0]) - getattr(inside[0], fields[0]))
            if valid_inner and len(inside) >= 2
            else None
        ),
        "upper": (
            factor * (getattr(outer[-1], fields[0]) - getattr(outer[0], fields[0]))
            if valid_outer
            else None
        ),
    }


def interval(rows, reason, finish):
    start_lo, start_hi = reason - MARGIN, reason + MARGIN
    end_lo, end_hi = finish - MARGIN, finish + MARGIN
    check(start_hi < end_lo, "client window")
    inside = [r for r in rows if r.lo >= start_hi and r.hi <= end_lo]
    left = next((i for i in reversed(range(len(rows))) if rows[i].hi <= start_lo), None)
    right = next((i for i, r in enumerate(rows) if r.lo >= end_hi), None)
    outer = rows[left : right + 1] if left is not None and right is not None else []
    relevant = [r for r in rows if r.hi >= start_lo and r.lo <= end_hi]
    # Unknown instant of each read lies between its lo and hi. Include the
    # uncovered edges, with no prolongation outside the client window.
    support = [
        Sample(start_lo, start_lo, 0, 0, 0, 0),
        *relevant,
        Sample(end_hi, end_hi, 0, 0, 0, 0),
    ]
    max_gap = max(min(end_hi, b.hi) - max(start_lo, a.lo) for a, b in pairwise(support))
    density = len(inside) >= 2 and max_gap <= MAX_GAP
    cgroup = counter_bounds(relevant, inside, outer, ("rbytes", "rios"))
    ios = counter_bounds(relevant, inside, outer, ("rios", "rbytes"))
    disk = counter_bounds(relevant, inside, outer, ("sectors",), 512)

    def span(seq):
        if not seq:
            return None
        return [[seq[0].lo, seq[0].hi], [seq[-1].lo, seq[-1].hi]]

    return dict(
        samples=len(rows),
        inside_samples=len(inside),
        window_ns=[reason, finish],
        cut_margin_ns=MARGIN,
        inside_endpoint_brackets_ns=span(inside),
        outside_endpoint_brackets_ns=span(outer),
        maximum_gap_upper_ns=max_gap,
        density="SUFFICIENT" if density else "INCONCLUSIVE",
        first_to_last_sample_ns=rows[-1].hi - rows[0].lo if rows else None,
        cgroup_submitted_read_bytes=cgroup,
        cgroup_read_bios=ios,
        namespace_completed_read_bytes=disk,
        observed_inflight_range=(
            [min(r.inflight for r in inside), max(r.inflight for r in inside)] if inside else None
        ),
    )


def price(first_final, span, lower, covered):
    check(0 < span <= first_final, "producer/client durations")
    remaining = 10**10 - (first_final - span)
    cap = max(0, remaining) * 8
    if remaining <= 0:
        status = "NO_TIME_IN_FIXED_EXTERIOR_SCENARIO"
    elif not covered or lower is None:
        status = "INCONCLUSIVE_ACCOUNTING"
    elif cap < lower:
        status = "CONDITIONAL_EXCLUSION_ABOVE_CRITICAL_FRACTION"
    else:
        status = "NO_EXCLUSION_FROM_OBSERVED_MINIMUM"
    return dict(
        classification=status,
        span_ns=span,
        fixed_exterior_ns=first_final - span,
        available_ns=remaining,
        max_bytes_at_8GBps=cap,
        observed_lower_bytes=lower,
        critical_fraction_of_lower=(cap / lower if covered and lower else None),
    )


def assess_history():
    prior = read(pin(PAST, "11f3ab3e7dba55b558fd77be1cf1430f7dd328d8880f8477f40ac32c23dffd9b"))
    check(prior["bandwidth_ceiling_B_s"] == 8_000_000_000, "historical link")
    result = {}
    for order in ("rop", "por"):
        arm = prior["arms"][order]
        lower = arm["counter_bounds"]["counters"]["read_bytes"]["min"]
        assessed = {}
        for name in CLOCKS:
            old = arm["budgets"][name]
            p = price(arm["first_final_ns"], old["observed_span_ns"], lower, True)
            check(
                old["steps"] == 44
                and (p["max_bytes_at_8GBps"], p["available_ns"])
                == (old["max_link_bytes"], old["remaining_ns"]),
                "historical arithmetic",
            )
            assessed[name] = p
        result[order] = dict(
            metric="PROCESS_READ_BYTES", arm_sha256=arm["arm_sha256"], clocks=assessed
        )
    return result


def grade_arm(arm: Path, trace: Path, inventory: dict) -> dict:
    check(
        inventory["namespace_dev"] == "259:0"
        and inventory["partition_dev"] == "259:3"
        and inventory["link_width"] == 4
        and inventory["link_speed"] == "16.0 GT/s PCIe",
        "namespace/partition/link inventory",
    )
    parent = run_path(
        pin(
            HERE.parent / "screen.py",
            "cd768e0a19a8eb7403ab70a24271b5a70ac8c889117aae4f254cba377721759f",
        )
    )
    clock = parent["CLOCK"]
    check(clock["MARGIN"] == MARGIN, "client margin")
    step = run_path(pin(STEP, "0f5db7f0f48df0f1109e04ce3643e46d06ab157ae25b5e98cfc026e35c9fef09"))
    arm_sha = sha(arm / "arm.json")
    past = assess_history()
    check(arm_sha not in {p["arm_sha256"] for p in past.values()}, "new independent P")
    priced = step["assess"](arm, arm_sha)
    check(priced["status"] == "CONDITIONAL_PACK_B3_COST", "producer text cut")
    meta = read(arm / "arm.json")
    grade = meta["grade"]
    receipt = read(arm / "receipt.json")
    raw = arm / "raw"
    client = read(arm / "client-receipt.json")
    (launch,) = raw.glob("*.launch.json")
    pid = read(pin(launch, client["launch_sha256"]))["process_identity"]
    check(
        pid == client["process_identity"] == inventory["process_identity"]
        and pid["pid"] == receipt["native_ids"]["pid"]
        and pid["cgroup_inode"] == inventory["cgroup_inode"] > 0,
        "server/sampler identity",
    )
    full = clock["read"](raw / "T2-result.json")
    journal = clock["lines"](raw / "T2-request.jsonl")
    check(
        full["accepted"]
        and journal[-1]["accepted"]
        and read(raw / "T2-result.json") == client["rows"][1],
        "accepted T2",
    )
    phase = full["stream_metrics"]
    ns = clock["ns"]
    start = ns(full["request_started_monotonic"])
    reason, finish = [
        start + ns(phase[key]) for key in ("first_reasoning_chunk_s", "first_final_content_chunk_s")
    ]
    for key, t in (("reasoning_content", reason), ("content", finish)):
        lo, hi = parent["endpoint"](journal, key)
        check(lo - MARGIN <= t <= hi + MARGIN, "client SSE endpoint " + key)
    check(abs(finish - start - priced["first_final_ns"]) <= 2, "client first final rounding")
    samples = read_trace(trace)
    obs = interval(samples, reason, finish)
    enough = obs["density"] == "SUFFICIENT"
    available = enough and obs["cgroup_submitted_read_bytes"]["lower"] is not None
    clocks = {}
    for name in CLOCKS:
        w = priced["windows"][name]
        check(
            w["evaluations_through_cut"] == 44
            and w["first_final_sample_one_based"] == 45
            and w["before_total_ns"] + w["after_total_ns"] == w["full_span_ns"],
            "44 steps + tail",
        )
        p = price(
            priced["first_final_ns"],
            w["before_total_ns"],
            obs["cgroup_submitted_read_bytes"]["lower"],
            available,
        )
        clocks[name] = dict(
            **p,
            evaluations=44,
            tail_ns=w["after_total_ns"],
            historical_process_class_matches={
                k: p["classification"] == v["clocks"][name]["classification"]
                for k, v in past.items()
            },
        )
    return dict(
        status=(
            "MEASURED_CGROUP_NVME_REQUEST_WINDOW"
            if available and obs["namespace_completed_read_bytes"]["lower"] is not None
            else "INCONCLUSIVE_DEVICE_OBSERVATION"
        ),
        arm_sha256=arm_sha,
        arm_receipt_sha256=priced["arm_receipt_sha256"],
        trace_sha256=sha(trace),
        protocol_sha256=sha(HERE / "protocol.md"),
        program_sha256=sha(Path(__file__)),
        prior_comparison_sha256=sha(PAST),
        historical=past,
        namespace_dev=inventory["namespace_dev"],
        partition_dev=inventory["partition_dev"],
        bandwidth_ceiling_B_s=8_000_000_000,
        observation=obs,
        producer_clocks=clocks,
        first_final_ns=priced["first_final_ns"],
        decode_ns=priced["decode_ns"],
        prefill_ns=priced["prefill_ns"],
        sampled_ids_sha256=priced["sampled_ids_sha256"],
        projected_sha256=priced["projected_sha256"],
        stderr_sha256=priced["stderr_sha256"],
        verified_ids_sha256=grade["verified_ids_sha256"],
        model_launches_graded=1,
        http_requests_graded=2,
        decode_excess_ns_at_six=priced["decode_ns"] - 47 * 10**9 // 6,
    )
