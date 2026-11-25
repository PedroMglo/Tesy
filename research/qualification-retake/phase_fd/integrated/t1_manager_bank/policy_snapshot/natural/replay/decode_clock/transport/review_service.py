"""Verify the scheduled byte identities, independent READ clocks, and four prices of the same T2."""

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
CLOCK = "f637152c0915ccbf33d4f70e101e9910a6aab2edd2d925a93f7ed6f250fe8f99"
SITE = ("step", "position", "call", "tile", "layer", "wave", "tier")
IDENTITY = ("ordinal", "expert", "slot", "generation")
GATES = {"six": 7_833_333_334, "joint": 5_959_223_099}
OUTSIDE = 2_318_241_276
VOLUMES = {"R": 10_545_446_912, "P": 10_537_844_736}
CASES = ("read_floor", "common_set_floor", "isolated_drain")


def check(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open("rb") as fp:
        return hashlib.file_digest(fp, "sha256").hexdigest()


def pinned(path, expected):
    check(not path.is_symlink() and digest(path) == expected, "identity of " + path.name)
    return json.loads(path.read_bytes())


def distribution(xs):
    if not xs:
        return {"n": 0}
    ordered = sorted(xs)
    return dict(
        n=len(xs),
        mean_ns=sum(xs) / len(xs),
        median_ns=median(xs),
        p05_ns=ordered[math.ceil(0.05 * len(xs)) - 1],
        p95_ns=ordered[math.ceil(0.95 * len(xs)) - 1],
        min_ns=ordered[0],
        max_ns=ordered[-1],
    )


def union(spans):
    right = total = 0
    for start, end in sorted(spans):
        check(type(start) is int and type(end) is int and 0 <= start < end, "READ endpoints")
        total += max(0, end - max(right, start))
        right = max(right, end)
    return total


def group(plan, raw, layout):
    check(all(raw[k] == plan[k] for k in SITE), "wrong logical group")
    jobs = plan["jobs"]
    disk = [j for j in jobs if j["source"] == "disk"]
    check(len(raw["jobs"]) == len(disk) <= len(jobs) <= 4, "jobs not in sole demand wave")
    counts = Counter()
    by_worker = defaultdict(list)
    read_by_ordinal = {}
    for planned, actual in zip(disk, raw["jobs"], strict=True):
        check(all(planned[k] == actual[k] for k in IDENTITY), "ordinal, binding or generation")
        components = planned["components"]
        check([p["role"] for p in components] == ["gate", "down", "up"], "role order")
        check(actual["component_sha256"] == [p["sha256"] for p in components], "payload digest")
        spans = actual["read_spans_ns"]
        check(len(spans) == (3 if layout == "R" else 1), "pread count")
        check(0 <= raw["release_ns"] <= spans[0][0], "READ before release")
        duration = sum(b - a for a, b in spans)
        check(union(spans) == duration and spans == sorted(spans), "serial job")
        by_worker[actual["worker"]].extend(spans)
        read_by_ordinal[planned["ordinal"]] = duration
        counts["preads"] += len(spans)
        counts["requested_bytes"] += (
            sum(p["aligned_bytes"] for p in components) if layout == "R" else planned["pack_bytes"]
        )
        counts["payload_bytes"] += sum(p["size_bytes"] for p in components)
    for spans in by_worker.values():
        check(union(spans) == sum(b - a for a, b in spans), "overlapping accesses on one worker")
    all_spans = [span for values in by_worker.values() for span in values]
    drain = raw["drain_ns"]
    observed_union = union(all_spans)
    check(max((b for _, b in all_spans), default=0) <= drain, "READ outside group")
    check(
        raw["read_worker_ns"] == sum(read_by_ordinal.values())
        and raw["read_union_ns"] == observed_union,
        "READ clocks",
    )
    check(bool(disk) or drain == raw["hash_ns"] == 0, "empty group priced")
    sets = [(j["r0_same_site_set_ns"] or 0) for j in jobs]
    chains = [s + read_by_ordinal.get(j["ordinal"], 0) for j, s in zip(jobs, sets, strict=True)]
    counts.update(
        groups=1,
        disk_groups=int(bool(disk)),
        disk_jobs=len(disk),
        bank_jobs=len(jobs) - len(disk),
        worker_ns=sum(read_by_ordinal.values()),
        union_ns=observed_union,
        isolated_drain=drain,
        hash_ns=raw["hash_ns"],
        read_floor=max(read_by_ordinal.values(), default=0),
        common_set_floor=max(chains, default=0),
        set_only=max(sets, default=0),
    )
    return counts, set(by_worker)


def review_arm(root, meta, groups, layout):
    original = meta["arms"][layout]
    path = root / "raw" / (layout + ".jsonl")
    check(digest(path) == original["groups_sha256"], "physical group logs")
    rows = [json.loads(s) for s in path.read_bytes().splitlines()]
    checks = {"CPU": Counter(), "CUDA0": Counter()}
    workers = set()
    drains = []
    steps = [0] * 46
    for p, row in zip(groups, rows, strict=True):
        c, seen = group(p, row, layout)
        checks[p["tier"]].update(c)
        workers.update(seen)
        steps[p["step"]] += c["isolated_drain"]
        drains.append(c["isolated_drain"] if c["disk_groups"] else None)
    total = checks["CPU"] + checks["CUDA0"]
    check(
        0 < len(workers) <= 4
        and total["groups"] == 1656
        and total["disk_jobs"] == 797
        and total["bank_jobs"] == 399
        and total["set_only"] == 522063311,
        "population or SET bridge",
    )
    check(
        total["requested_bytes"] == original["requested_bytes"] == VOLUMES[layout]
        and total["payload_bytes"] == original["payload_bytes"] == 10535702400,
        "payload or padding",
    )
    for k, old in (
        ("worker_ns", "read_worker_ns"),
        ("union_ns", "read_union_ns"),
        ("isolated_drain", "drain_ns"),
        ("hash_ns", "hash_ns"),
    ):
        check(total[k] == original[old], "clock " + old)
    check(
        original["wall_ns"]
        == total["isolated_drain"]
        + total["hash_ns"]
        + original["monitor_ns"]
        + original["residual_ns"]
        and original["residual_ns"] >= 0
        and original["components"] == 2391,
        "wall and component accounting",
    )
    clocks = {}
    for key in CASES:
        duration = OUTSIDE + total[key]
        clocks[key] = dict(
            inside_ns=total[key],
            total_ns=duration,
            max_tokens_s=47e9 / duration,
            margin_ns={gate: limit - duration for gate, limit in GATES.items()},
            margin_ns_per_admission={
                gate: (limit - duration) / 1196 for gate, limit in GATES.items()
            },
        )
    report = dict(
        by_tier=checks,
        all=dict(total),
        expected_data_sha256=original["groups_sha256"],
        workers_with_disk_jobs=len(workers),
        conditional=clocks,
        read_group_drain_distribution=distribution([x for x in drains if x is not None]),
        per_step_drain_distribution=distribution(steps),
        envelope_ns=original["wall_ns"],
        monitor_ns=original["monitor_ns"],
        residual_ns=original["residual_ns"],
        whole_device_delta=original["disk_delta"],
    )
    return report, drains, steps


def resources(root, meta):
    inv = pinned(root / "inventory.json", meta["inventory_sha256"])
    check(
        inv["duration_s"] >= 60 and inv["cap_bytes"] == meta["cap_bytes"] == 384 << 20,
        "60s admission and scope",
    )
    cap = meta["stop_bytes"]
    check(
        0 < meta["cgroup_peak_bytes"] < cap == 336 << 20
        and meta["gpu_compute"] == meta["model_forwards"] == 0,
        "operator resources",
    )
    raw = root / "raw"
    samples = raw / Path(inv["path"]).name
    check(digest(samples) == inv["sha256"], "admission samples")
    tel = raw / "telemetry.jsonl"
    check(digest(tel) == meta["telemetry_sha256"], "operation samples")
    obs = [json.loads(s) for s in tel.read_bytes().splitlines()]
    times = [datetime.fromisoformat(x["utc"]) for x in obs]
    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
    check(
        gaps
        and min(gaps) > 0
        and max(gaps) < 3
        and max(x["peak_bytes"] for x in obs) <= meta["cgroup_peak_bytes"],
        "monitor coverage",
    )
    return dict(
        cgroup_peak_bytes=meta["cgroup_peak_bytes"],
        inventory_s=inv["duration_s"],
        monitor_samples=len(obs),
        max_monitor_gap_s=max(gaps),
        cleanup_ns=meta["cleanup_ns"],
        source_sha256={k: v["layout_sha256"] for k, v in meta["sources"].items()},
        max_gpu_temperature_c=max(x["observation"]["gpu"]["temperature_c"] for x in obs),
        max_cpu_temperature_c=max(x["observation"]["thermal"]["cpu_tctl_c"] for x in obs),
    )


def audit(a):
    plan = pinned(a.plan, a.plan_sha256)
    check(plan["clock_sha256"] == CLOCK and len(plan["groups"]) == 1656, "decode clock and plan")
    rows, contrasts, witnesses = {}, [], {}
    for i, (order, root, h) in enumerate(
        (("RP", a.first, a.first_sha256), ("PR", a.second, a.second_sha256)), 1
    ):
        meta = pinned(root / "receipt.json", h)
        check(
            meta["status"] == "PASS_DECODE_NVME_SERVICE_PAIR"
            and meta["process"] == i
            and meta["order"] == order
            and meta["plan_sha256"] == a.plan_sha256,
            "physical family",
        )
        check(meta["prior_receipt_sha256"] == (None if i == 1 else a.first_sha256), "pair order")
        witnesses[order] = resources(root, meta)
        row = rows[order] = {}
        vectors = {}
        for arm in order:
            row[arm], groups, steps = review_arm(root, meta, plan["groups"], arm)
            vectors[arm] = groups, steps
        positive = []
        for x, y in zip(vectors["R"][0], vectors["P"][0], strict=True):
            check((x is None) == (y is None), "matched active sets")
            if x is not None:
                positive.append(x - y)
        r, p = row["R"]["all"], row["P"]["all"]
        step_deltas = [x - y for x, y in zip(vectors["R"][1], vectors["P"][1], strict=True)]
        contrasts.append(
            dict(
                order=order,
                drain_saved_ns=r["isolated_drain"] - p["isolated_drain"],
                relative_drain_saving=1 - p["isolated_drain"] / r["isolated_drain"],
                by_tier_drain_saved_ns={
                    tier: row["R"]["by_tier"][tier]["isolated_drain"]
                    - row["P"]["by_tier"][tier]["isolated_drain"]
                    for tier in ("CPU", "CUDA0")
                },
                faster_populated_groups=sum(x > 0 for x in positive),
                faster_steps=sum(x > 0 for x in step_deltas),
                populated_group_delta=distribution(positive),
                step_delta=distribution(step_deltas),
            )
        )
    gates = {}
    for layout in ("R", "P"):
        gates[layout] = {}
        for case in CASES:
            gates[layout][case] = {}
            for gate in GATES:
                flags = [
                    rows[o][layout]["conditional"][case]["margin_ns"][gate] >= 0
                    for o in ("RP", "PR")
                ]
                gates[layout][case][gate] = (
                    "HEADROOM_ONLY"
                    if all(flags)
                    else "INCONCLUSIVE"
                    if any(flags)
                    else "NO_GO_FIXED_PRICES"
                )
    return dict(
        status="REPRODUCED_FOUR_TRANSPORT_ARMS",
        plan_sha256=a.plan_sha256,
        raw_receipt_sha256=[a.first_sha256, a.second_sha256],
        gates=gates,
        arms=rows,
        resources=witnesses,
        paired=contrasts,
        program_sha256=digest(Path(__file__)),
        protocol_sha256=digest(HERE / "review-protocol.md"),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("plan", "first", "second", "new-output-dir"):
        p.add_argument("--" + arg, required=True, type=Path)
    for arg in ("plan-sha256", "first-sha256", "second-sha256"):
        p.add_argument("--" + arg, required=True)
    a = p.parse_args()
    out = a.new_output_dir
    out.mkdir(mode=0o700)
    try:
        result = audit(a)
    except (KeyError, IndexError, ValueError, TypeError, OSError) as exc:
        result = dict(status="FAIL_PRESERVED", failure=f"{type(exc).__name__}: {exc}")
    tmp = out / "incoming.json"
    with tmp.open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    tmp.rename(out / "receipt.json")
    print(result["status"], result.get("failure", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
