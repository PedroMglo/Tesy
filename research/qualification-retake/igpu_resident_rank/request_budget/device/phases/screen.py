"""Subsequent offline analysis of two ordered native phases in one sealed P arm."""

import argparse
import json
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from itertools import pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parents[3]
GRADE = run_path(HERE.parent / "grade.py")
sha, read, check = (GRADE[k] for k in ("sha", "read", "check"))
ARCHIVE = "84c1c8ae105a8967c4502cdb014979b850b3d9c2a065b2a9d9cd9939425f4266"
TERMINAL = "ea74c80eafd0038753454c0a3ee2f5266205d805d872ce4827babd6817e54c41"
MARGIN = 2000
NS = 10**9


def envelope(s, e, prompt_ms, decode_ms):
    """Decimal values in the client/server wire representation, rounded outwards once."""
    s, e = s * NS, e * NS
    p, d = prompt_ms * 10**6, decode_ms * 10**6
    check(0 < s < e and min(p, d) > 0 and s + p + d <= e, "invalid serial client/native clocks")

    def low(t):
        return int(t.to_integral_value(rounding=ROUND_FLOOR)) - MARGIN

    def high(t):
        return int(t.to_integral_value(rounding=ROUND_CEILING)) + MARGIN

    return (
        dict(
            prompt=(low(s), high(e - p - d), low(s + p), high(e - d)),
            decode=(low(s + p), high(e - d), low(s + p + d), high(e)),
        ),
        dict(
            prompt_ns=str(p.normalize()),
            decode_ns=str(d.normalize()),
            client_residual_ns=str((e - s - p - d).normalize()),
            client_elapsed_ns=str((e - s).normalize()),
        ),
    )


def phase(rows, bounds):
    s_min, s_max, e_min, e_max = bounds
    # There may be no guaranteed interior if the client residual is wide.
    inside = [r for r in rows if s_max < r.lo and r.hi < e_min]
    left = next((i for i in reversed(range(len(rows))) if rows[i].hi < s_min), None)
    right = next((i for i, r in enumerate(rows) if e_max < r.lo), None)
    outer = rows[left : right + 1] if left is not None and right is not None else []
    possible = [r for r in rows if r.hi >= s_min and r.lo <= e_max]
    # Upper bound on the gap between unknown observation instants, including both edges.
    points = [(s_min, s_min), *((v.lo, v.hi) for v in possible), (e_max, e_max)]
    gap = max(min(e_max, b[1]) - max(s_min, a[0]) for a, b in pairwise(points))
    bounds_for = GRADE["counter_bounds"]
    fields = dict(
        cgroup_submitted_rbytes=bounds_for(possible, inside, outer, ("rbytes", "rios")),
        cgroup_rios=bounds_for(possible, inside, outer, ("rios", "rbytes")),
        namespace_read_sectors=bounds_for(possible, inside, outer, ("sectors",)),
    )
    sectors = fields["namespace_read_sectors"]
    fields["namespace_completed_read_bytes"] = {
        k: (512 * v if k in ("lower", "upper") and v is not None else v) for k, v in sectors.items()
    }
    sparse = len(inside) < 2 or gap > GRADE["MAX_GAP"]
    usable = not sparse and all(v["lower"] is not None for v in fields.values())
    return dict(
        status="BOUNDED_NATIVE_PHASE" if usable else "INCONCLUSIVE_PHASE_OBSERVATION",
        phase_bounds_ns=list(bounds),
        inside_samples=len(inside),
        possible_samples=len(possible),
        max_gap_upper_ns=gap,
        density="INCONCLUSIVE" if sparse else "SUFFICIENT",
        inside_brackets_ns=[[v.lo, v.hi] for v in (inside[0], inside[-1])] if inside else None,
        outer_brackets_ns=[[v.lo, v.hi] for v in (outer[0], outer[-1])] if outer else None,
        counters=fields,
    )


def clock_input(arm, i, client, grade):
    def parse(path):
        return json.loads(path.read_bytes(), parse_float=Decimal)

    full = parse(arm / "raw" / f"T{i}-result.json")
    journal = [
        json.loads(line, parse_float=Decimal)
        for line in (arm / "raw" / f"T{i}-request.jsonl").read_bytes().splitlines()
    ]
    row = grade["rows"][i - 1]
    receipt_row = parse(arm / "receipt.json")["rows"][i - 1]
    geom = ((2043, 0, 78), (2197, 2044, 47))[i - 1]
    check(
        full["accepted"] is True
        and full == client["rows"][i - 1]
        and journal[-1]["accepted"]
        and all(j["request_id"] == full["id"] for j in journal)
        and [j["kind"] for j in journal if j["kind"] != "SSE_FRAGMENT"]
        == ["REQUEST_START", "RESPONSE_COMPLETE", "REQUEST_TERMINAL"],
        "turn/stream authority",
    )
    frames = [
        json.loads(j["fragment"][6:], parse_float=Decimal)
        for j in journal
        if j["kind"] == "SSE_FRAGMENT" and j.get("fragment", "").startswith("data: {")
    ]
    t = full["timings"]
    s, e = full["request_started_monotonic"], full["request_ended_monotonic"]
    check(
        frames[-1]["timings"]
        == t
        == full["response"]["timings"]
        == journal[-2]["response"]["timings"]
        and t == parse(arm / "raw" / f"T{i}-timings-observed.json")
        and [f["__verbose"]["timings"] for f in frames if "__verbose" in f] == [t]
        and s <= journal[0]["monotonic_s"] <= journal[-2]["completed_monotonic"] == e
        and e <= journal[-1]["monotonic_s"]
        and all(a["monotonic_s"] <= b["monotonic_s"] for a, b in pairwise(journal)),
        "timestamps or final SSE price",
    )
    check(
        (row["input_n"], t["cache_n"], t["predicted_n"]) == geom
        and t["prompt_n"] == geom[0] - geom[1]
        and receipt_row["id"] == row["id"] == full["id"]
        and receipt_row["official_ids_sha256"] == row["official_ids_sha256"]
        and abs(t["predicted_ms"] / 1000 - receipt_row["decode_s"]) <= Decimal("0.000000001")
        and abs(t["prompt_ms"] / 1000 - receipt_row["prefill_s"]) <= Decimal("0.000000001"),
        "official work or prices",
    )
    return envelope(s, e, t["prompt_ms"], t["predicted_ms"])


def screen(archive):
    root = archive / "part-88/tesy-device-budget-natural-20261125-r01"
    entry = read(HERE.parent / "archive-88.json")
    check(
        entry["manifest"]["sha256"] == ARCHIVE and sha(root.parent / "manifest.json") == ARCHIVE,
        "archived manifest",
    )
    ar = run_path(QUAL / "private_archive/verify.py")
    ar["verify"](archive, entry)
    check(sha(root / "receipt.json") == TERMINAL, "archived device receipt")
    family = read(root / "receipt.json")
    arm, trace = root / "P", root / "samples.tsv"
    regraded = GRADE["grade_arm"](arm, trace, family["observation"]["inventory"])
    check(
        family["grade"] == regraded
        and family["status"] == regraded["status"] == "MEASURED_CGROUP_NVME_REQUEST_WINDOW"
        and sha(trace) == family["trace_sha256"],
        "device/P regrade",
    )
    rows = GRADE["read_trace"](trace)
    client = json.loads((arm / "client-receipt.json").read_bytes(), parse_float=Decimal)
    g = read(arm / "arm.json")["grade"]
    turns = {}
    for i in (2, 1):
        ranges, times = clock_input(arm, i, client, g)
        turns[f"T{i}"] = dict(
            times=times,
            phases={n: phase(rows, b) for n, b in ranges.items()},
            official_ids_sha256=g["rows"][i - 1]["official_ids_sha256"],
            sampled_ids_sha256=g["trajectories"][i - 1]["sampled_ids_sha256"],
        )
    ok = all(v["status"] == "BOUNDED_NATIVE_PHASE" for v in turns["T2"]["phases"].values())
    return dict(
        status="BOUNDED_T2_NATIVE_PHASES" if ok else "INCONCLUSIVE_T2_NATIVE_PHASES",
        classification="EXPLORATORY_FROZEN_AFTER_MEASUREMENT",
        terminal_sha256=TERMINAL,
        trace_sha256=sha(trace),
        archive_manifest_sha256=ARCHIVE,
        device_rows=len(rows),
        arm_sha256=family["arm_sha256"],
        program_sha256=sha(Path(__file__)),
        protocol_sha256=sha(HERE / "protocol.md"),
        observations_acquired=0,
        model_launches=0,
        turns=turns,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = screen(a.archive)
    except Exception as exc:
        result = dict(
            status="INCONCLUSIVE_AUTHORITY_OR_INPUT", reason=f"{type(exc).__name__}: {exc}"
        )
    with (a.new_output_dir / "receipt.json").open("x") as f:
        print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False), file=f)
    print(result["status"], result.get("reason", ""))
    raise SystemExit(int(result["status"] == "INCONCLUSIVE_AUTHORITY_OR_INPUT"))
