"""Bound same-router releases using separate, measured per-job read prices."""

import argparse
import collections
import hashlib
import importlib.util
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
INT = HERE.parent
spec = importlib.util.spec_from_file_location("pfj_for_router", INT / "analyse.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
need = audit.check
P = "196e94e9b3c267d0821edfe57ddd7508c6ea3380e72b46a11570c33f753723e2"
BASE = "47476b0d8f0435c5e4c04f56a73edbb85f81e22ef9f9ba80a92c3b19b67d5b74"


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def pinned(path, digest):
    need(sha(path) == digest, "source " + path.name)
    return json.loads(path.read_bytes())


def cells(rows):
    out = {}
    site = None
    for r in rows:
        k = (r.call, r.tile, r.layer)
        if r.kind == 9:
            if k not in out:
                out[k] = []
            need(site is None and next(reversed(out)) == k, "interleaved layer/tile")
            site = (k, r.wave, r.ns)
        if r.kind == 23:
            need(site is not None and (k, r.wave) == site[:2], "remap pairing")
            group = out[k]
            need(not group or group[-1][1] <= site[2], "overlap between waves")
            group.append((site[2], r.ns, r.wave))
            site = None
    need(site is None and out, "unfinished remap")
    return out


def charge(work, gaps):
    return max(0, max(max(work), sum(work) // 4) - gaps) if work else 0


def estimate(groups, service, start, first, residual, expanded):
    previous = start
    costs = collections.Counter()
    eligible = used = 0
    for k, waves in groups.items():
        begin = previous if expanded else waves[0][0]
        end = waves[-1][1]
        need(previous <= waves[0][0] and begin <= end, "cell overlap")
        previous = end
        work = [n for _, _, w in waves for n in service.get((*k, w), ())]
        eligible += len(work)
        if end > first - 10**6 or begin < start:
            continue
        active = sum(b - a for a, b, _ in waves)
        credit = end - begin - active
        need(credit >= 0, "negative cell gap")
        scope = "prefill" if k[0] <= 2 else "decode_before_first_final"
        if work:
            costs[scope + "_service_floor_ns"] += charge(work, 0)
            costs[scope + "_exposed_floor_ns"] += charge(work, credit)
            costs[scope + "_credited_ns"] += charge(work, 0) - charge(work, credit)
        used += len(work)
    need(eligible == 875, "missing plan jobs")
    total = (
        residual
        + costs["prefill_exposed_floor_ns"]
        + costs["decode_before_first_final_exposed_floor_ns"]
    )
    return {
        "jobs_with_deadline_before_first_final": used,
        "excluded_crossing_jobs": eligible - used,
        "ns": dict(costs),
        "first_final_floor_ns": total,
        "excess_ns": total - 10**10,
        "decision": "NO_GO_AT_MEASURED_PRICES" if total > 10**10 else "HEADROOM_ONLY",
    }


def run(args):
    base = pinned(INT / "nominal-r01/limits.json", BASE)
    plan = pinned(args.plan, P)
    journal = args.on_dir / "raw/events.pfj"
    records, header = audit.read_journal(journal)
    need(header["journal_sha256"] == base["sources"]["journal"], "journal identity")
    arch = pinned(args.archive_manifest, base["sources"]["private_raw_manifest"])
    raw = pinned(
        args.on_dir / "raw/T2-result.json",
        arch["files"][args.on_dir.name + "/raw/T2-result.json"]["sha256"],
    )
    start = int(raw["request_started_monotonic"] * 10**9)
    first = start + int(raw["stream_metrics"]["first_final_content_chunk_s"] * 10**9)
    residual = base["mandatory_service"]["fixed_outside_callbacks_ns"]["first"]
    groups = cells(records)
    arms = []
    for arm, (root, digest) in enumerate(zip(args.arm_dir, args.arm_sha, strict=True), 1):
        r = pinned(root / "receipt.json", digest)
        need(
            r["status"].startswith("PASS")
            and r["arm"] == arm
            and r["plan_sha256"] == P
            and r["components"] == 2625,
            "arm identity",
        )
        raw_groups = root / "raw/groups.jsonl"
        need(sha(raw_groups) == r["groups_sha256"], "service identity")
        rows = [json.loads(line) for line in raw_groups.read_text().splitlines()]
        service = {}
        for orig, row in zip(plan["groups"], rows, strict=True):
            key = tuple(orig["site"])
            need(key == tuple(row["site"]) and key not in service, "site identity")
            values = []
            for src, job in zip(orig["experts"], row["jobs"], strict=True):
                need(
                    src["expert"] == job["expert"] and len(job["read_spans_ns"]) == 3,
                    "job identity",
                )
                values.append(sum(b - a for a, b in job["read_spans_ns"]))
            service[key] = values
        need(
            sum(map(len, service.values())) == 875
            and sum(charge(v, 0) for v in service.values()) == r["floor_ns"],
            "original cost",
        )
        arms.append(
            {
                "receipt_sha256": digest,
                "same_router": estimate(groups, service, start, first, residual, False),
                "previous_last_callback": estimate(groups, service, start, first, residual, True),
            }
        )
    need(len(arms) == 2, "two arms")
    outcome = {}
    for mode in ("same_router", "previous_last_callback"):
        labels = {a[mode]["decision"] for a in arms}
        outcome[mode] = next(iter(labels)) if len(labels) == 1 else "INCONCLUSIVE"
    return {
        "status": "PASS_OFFLINE_ROUTER_RELEASE",
        "outcome": outcome,
        "arms": arms,
        "rest_ns": residual,
        "scope": "natural T2 first final, conditional measured service",
        "protocol_sha256": sha(HERE / "protocol.md"),
        "code_sha256": sha(Path(__file__)),
        "source_limits_sha256": BASE,
        "source_plan_sha256": P,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for opt in ("on-dir", "archive-manifest", "plan", "new-output-dir"):
        p.add_argument("--" + opt, required=True, type=Path)
    p.add_argument("--arm-dir", type=Path, nargs=2, required=True)
    p.add_argument("--arm-sha", nargs=2, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(exist_ok=False)
    receipt = a.new_output_dir / "receipt.json"
    try:
        r = run(a)
    except Exception as e:
        receipt.write_text(json.dumps({"status": "FAIL", "reason": str(e)}, indent=2) + "\n")
        raise
    receipt.write_text(json.dumps(r, indent=2, sort_keys=True) + "\n")
