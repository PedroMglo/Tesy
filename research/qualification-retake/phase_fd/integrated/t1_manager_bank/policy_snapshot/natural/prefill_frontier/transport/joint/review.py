"""Reprice the original T2 using independent measurements of prefill and decode transport."""

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
FRONTIER_SHA = "5225590f4a5ea17f7faa1d13fede10dc9abc771d53dbc388333709a4d86765c2"
BYTES = {"R": 13998665728, "P": 13988757504}
PAYLOAD = 13985913600
from_budget = run_path(HERE / "budget.py")


def check(ok, msg):
    if not ok:
        raise ValueError(msg)


def sha(path):
    with path.open("rb") as fp:
        return hashlib.file_digest(fp, "sha256").hexdigest()


def pinned(path, digest):
    check(not path.is_symlink() and sha(path) == digest, "invalid seal: " + path.name)
    return json.loads(path.read_bytes())


def occupancy(spans, elapsed):
    changes = Counter()
    for lo, hi in spans:
        check(type(lo) is int and type(hi) is int and 0 <= lo < hi <= elapsed, "pread outside call")
        changes[lo] += 1
        changes[hi] -= 1
    at = active = 0
    hist = [0] * 5
    for time, delta in sorted(changes.items()):
        hist[active] += time - at
        active += delta
        check(0 <= active <= 4, "worker concurrency")
        at = time
    check(active == 0, "outstanding pread at drain")
    hist[0] += elapsed - at
    return hist


def inspect_jobs(rows, expected, layout, summary):
    workers = defaultdict(list)
    acquired = 0
    for index, (row, (group, job)) in enumerate(zip(rows, expected, strict=True)):
        check(
            row["index"] == index
            and all(row[k] == group[k] for k in ("tier", "layer", "wave", "tile"))
            and all(
                row[k] == job[k]
                for k in ("ordinal", "expert", "slot", "generation", "source_enqueue")
            ),
            "timed job order/generation",
        )
        check(acquired <= row["acquired_ns"] <= row["read_spans_ns"][0][0], "FIFO acquisition")
        acquired = row["acquired_ns"]
        spans = row["read_spans_ns"]
        check(len(spans) == (1 if layout == "P" else 3), "component pread count")
        workers[row["worker"]].extend(spans)
    check(0 < len(workers) <= 4, "worker set")
    spans = []
    for seq in workers.values():
        seq.sort()
        check(
            all(x[1] <= y[0] for x, y in zip(seq, seq[1:], strict=False)), "overlap on one worker"
        )
        spans.extend(seq)
    elapsed = summary["dispatch_to_drain_ns"]
    hist = occupancy(spans, elapsed)
    check(
        sum(hist[1:]) == summary["read_union_ns"]
        and sum(i * v for i, v in enumerate(hist)) == summary["read_worker_ns"],
        "call clocks",
    )
    check(hist == [summary["qd_wall_ns"][str(i)] for i in range(5)], "inflight duration")
    return hist


def inspect_integrity(line, expected):
    for index, (row, (g, j)) in enumerate(zip(line["jobs"], expected, strict=True)):
        check(
            row["index"] == index
            and all(row[k] == g[k] for k in ("tier", "layer", "wave", "tile"))
            and all(
                row[k] == j[k]
                for k in ("ordinal", "expert", "slot", "generation", "source_enqueue")
            ),
            "integrity job order",
        )
        check(
            row["component_sha256"] == [c["sha256"] for c in j["components"]],
            "integrity traversal weight digest",
        )


def calculate(a):
    frontier = pinned(HERE.parents[1] / "evidence/receipt.json", FRONTIER_SHA)
    plan = pinned(a.plan, a.plan_sha256)
    schedules = {n: [] for n in (5, 148)}
    for g in plan["groups"]:
        for j in g["jobs"]:
            if j["source"] == "disk":
                schedules[g["call_tokens"]].append((g, j))
    check([len(v) for v in schedules.values()] == [34, 1024], "release population")
    arms = {}
    rows = {}
    last = None
    for order, root, digest in (("RP", a.first, a.first_sha256), ("PR", a.second, a.second_sha256)):
        receipt = pinned(root / "receipt.json", digest)
        check(
            receipt["status"] == "PASS_PREFILL_FULL_QUEUE_PAIR"
            and receipt["order"] == order
            and receipt["prior_receipt_sha256"] == last
            and receipt["plan_sha256"] == a.plan_sha256,
            "physical pair not admitted",
        )
        check(
            sha(root / "inventory.json") == receipt["inventory_sha256"]
            and sha(root / "raw/telemetry.jsonl") == receipt["telemetry_sha256"],
            "monitor coverage",
        )
        check(
            receipt["frontier_sha256"] == FRONTIER_SHA
            and receipt["cgroup_peak_bytes"] < receipt["stop_bytes"] == 336 << 20
            and receipt["model_forwards"] == receipt["gpu_compute"] == 0,
            "scope resources",
        )
        last = digest
        arms[order] = {}
        for layout in order:
            totals = receipt["arms"][layout]
            raw = root / "raw" / (layout + ".jsonl")
            verified = root / "raw" / (layout + "-integrity.jsonl")
            check(
                sha(raw) == totals["raw_sha256"]
                and sha(verified) == totals["verification_sha256"]
                and totals["verified_components"] == 3174,
                "timed/verified population",
            )
            calls = []
            lines = [json.loads(s) for s in raw.read_bytes().splitlines()]
            reread = [json.loads(s) for s in verified.read_bytes().splitlines()]
            for line, full, summary, (tokens, expected) in zip(
                lines, reread, totals["calls"], schedules.items(), strict=True
            ):
                check(full["call"] == line["call"] and full["call_tokens"] == tokens, "reread call")
                inspect_integrity(full, expected)
                check(
                    line["call_tokens"] == summary["call_tokens"] == tokens
                    and summary["call"] == line["call"] == expected[0][0]["call"],
                    "release identity",
                )
                elapsed = summary["dispatch_to_drain_ns"]
                check(
                    elapsed == line["elapsed_ns"] > 0 and summary["job_count"] == len(expected),
                    "call elapsed length",
                )
                histogram = inspect_jobs(line["jobs"], expected, layout, summary)
                need_bytes = sum(
                    sum(c["aligned_bytes"] for c in j["components"])
                    if layout == "R"
                    else j["pack_bytes"]
                    for _, j in expected
                )
                logical = sum(c["size_bytes"] for _, j in expected for c in j["components"])
                check(
                    logical == summary["logical_bytes"]
                    and need_bytes == summary["requested_bytes"],
                    "volume of the planned call",
                )
                calls.append(
                    dict(
                        tokens=tokens,
                        jobs=len(expected),
                        elapsed_ns_at_n_inflight_preads=histogram,
                        payload_bytes=logical,
                        requested_bytes=need_bytes,
                        service_ns=elapsed,
                        useful_bytes_per_s=logical * 1e9 / elapsed,
                    )
                )
            elapsed = sum(c["service_ns"] for c in calls)
            check(
                sum(c["payload_bytes"] for c in calls) == totals["logical_bytes"] == PAYLOAD
                and sum(c["requested_bytes"] for c in calls)
                == totals["requested_bytes"]
                == BYTES[layout]
                and elapsed == totals["dispatch_to_drain_ns"],
                "whole service",
            )
            arms[order][layout] = dict(
                calls=calls, service_ns=elapsed, useful_bytes_per_s=PAYLOAD * 1e9 / elapsed
            )
        saving = arms[order]["R"]["service_ns"] - arms[order]["P"]["service_ns"]
        rows[order] = dict(
            service_saved_ns=saving, fraction=saving / arms[order]["R"]["service_ns"]
        )
    return dict(
        status="REPRODUCED_PREFILL_TRANSPORT_AND_PHASE_COSTS",
        arms=arms,
        paired=rows,
        plan_sha256=a.plan_sha256,
        raw_receipt_sha256=[a.first_sha256, a.second_sha256],
        conditional=from_budget["cross"](
            frontier, {order: d["P"]["service_ns"] for order, d in arms.items()}
        ),
        frontier_sha256=FRONTIER_SHA,
        protocol_sha256=sha(HERE / "protocol.md"),
        program_sha256=sha(Path(__file__)),
        budget_sha256=sha(HERE / "budget.py"),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "first", "second", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    for name in ("plan", "first", "second"):
        p.add_argument("--" + name + "-sha256", required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        result = calculate(a)
    except Exception as exc:
        result = dict(status="FAIL_PRESERVED", cause=f"{type(exc).__name__}: {exc}")
    with (a.new_output_dir / "receipt.json").open("x") as fp:
        json.dump(result, fp, sort_keys=True, indent=2, allow_nan=False)
        fp.write("\n")
    print(result["status"], result.get("cause", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
