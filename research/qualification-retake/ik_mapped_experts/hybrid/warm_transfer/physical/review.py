"""Reprice the two closed CUDA processes from receipts and native rows only."""

import argparse
import json
from datetime import datetime
from pathlib import Path
from runpy import run_path
from statistics import median
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
WARM = HERE.parent
G = run_path(str(WARM / "grade.py"))
R = run_path(str(WARM.parent / "device/review.py"))
A = R["API"]
need, digest, bound = R["need"], R["digest"], R["bound"]
B = G["PAYLOAD"]
REPLAY = "8dd73ee6625e0d7dc2e93f2f6cf919c390fad6eb5d91391e06f89ddd2db588db"
ORDERS = ("FILE_FIRST", "ANON_FIRST")


def price(count, seconds_n, seconds_d, wall_ns, total_ns, n):
    """Compare to the exact rational target. Wall is per-fill, total covers n."""
    budget = seconds_n * 10**9
    return dict(
        fills=count,
        payload_B=count * B,
        seconds_num=seconds_n,
        seconds_den=seconds_d,
        required_B_s=count * B * seconds_d / seconds_n,
        max_ns_per_fill=budget / (seconds_d * count),
        fits_median=count * wall_ns * seconds_d <= budget,
        fits_aggregate=count * total_ns * seconds_d <= n * budget,
        serial_median_ns=count * wall_ns,
        remaining_ns_at_median=budget / seconds_d - count * wall_ns,
    )


def arm(family, name, r, policy, end, build, sealed):
    p = family / name
    hashes = {
        k: r[k]
        for k in (
            "samples_sha256",
            "maps_sha256",
            "stdout_sha256",
            "stderr_sha256",
            "monitor_sha256",
        )
    }
    for field, rel in zip(
        hashes,
        ("native/samples.json", "native/maps", "stdout", "stderr", "monitor.jsonl"),
        strict=True,
    ):
        need(digest(p / rel) == hashes[field], rel)
    need(json.loads((p / "grade.json").read_bytes()) == r, "saved arm grade")
    stats = G["reopen"](p)
    need(stats == r["grade"], "native grade drift")
    need(r["starts"] == 1 and r["child_gone"] and r["returncode"] == 0, "drain")
    mapped = R["mapped_names"](
        p / "native",
        r,
        dict(binary="warm-transfer", closure=build["loader"], binary_sha256=build["binary_sha256"]),
        sealed,
    )
    inv = r["admission"]
    ip = family / "raw" / (inv["run_id"] + ".start-inventory.jsonl")
    need(
        inv["run_id"] == family.name + "-" + name.lower() and Path(inv["path"]).name == ip.name,
        "C118 arm",
    )
    entries = R["lines"](ip)
    need(0 <= (datetime.fromisoformat(entries[0]["utc"]) - end).total_seconds() < 3300, "C55 age")
    A["INV"].require_inventory(
        family,
        inv["run_id"],
        inv | {"path": str(ip)},
        policy=policy,
        cap_bytes=A["CAP"],
        expected_power=A["INV"].POWER,
        now=datetime.fromisoformat(r["launch_utc"]),
    )
    monitor = R["lines"](p / "monitor.jsonl")
    window = R["check_window"](monitor, True, r["pid"], policy)
    sensors = R["bounds"](monitor)
    need(
        window["covered"] == r["observed_handoffs"] == 3
        and window["after_exit"]
        and window["last_sample_elapsed_s"] <= r["wall_s"] < 30
        and sensors["gpu_used_mib_max"] == r["sampled_vram_mib_max"]
        and R["bounds"](entries)["gpu_used_mib_max"] < A["VRAM"],
        "arm coverage",
    )
    data = json.loads((p / "native/samples.json").read_bytes())
    rows = data["rows"][2:]
    times = [{k: v for k, v in row.items() if k.endswith("_ns") or k == "mode"} for row in rows]
    return dict(
        hashes=hashes,
        grade=stats,
        priced_rows=times,
        c118_sha256=inv["sha256"],
        c118_s=inv["duration_s"],
        c118_samples=len(entries),
        monitor=sensors,
        window=window,
        provider_counts={k: len(v) for k, v in mapped.items()},
        mincore_pages_each=data["rows"][0]["pages_before"],
        starts=r["starts"],
        child_gone=r["child_gone"],
        endpoint_wall_s=r["wall_s"],
        minor_faults_priced=sum(x["minor_faults"] for x in rows),
    )


def review(a):
    family = a.family.resolve()
    r = bound(family / "receipt.json", a.family_sha256)
    need(
        r["status"] == "MEASURED_HOT_SHMEM_TO_IK_CUDA"
        and set(r["arms"]) == set(ORDERS)
        and r["model_loads"] == r["swap_peak_bytes"] == 0
        and 0 < r["max_scope_bytes"] < A["STOP"]
        and r["energy_j"] is None,
        "family",
    )
    ident = r["identity"]
    build = bound(a.build / "receipt.json", ident["build_sha256"])
    pre = bound(a.prepared / "receipt.json", a.prepared_sha256)
    need(
        pre["status"] == "PREPARED_ONLY"
        and pre["sealed"] == r["sealed"]
        and pre["identity"] == ident
        and build["status"] == "PASS_HOT_TRANSFER_BUILD"
        and build["dso_sha256"] == ident["dso_sha256"],
        "preflight/build",
    )
    for k in ("protocol.md", "grade.py", "transfer.cpp", "run.py"):
        need(digest(WARM / k) == build["source_sha256"][k], "source drift: " + k)
    policy, end = A["c55"](
        SimpleNamespace(c55=a.c55 / "receipt.json", c55_sha256=ident["c55_sha256"])
    )
    phases = bound(WARM.parent / "natural_link/classlru/two_steps/result.json", REPLAY)["phases"]
    arms, all_rows = {}, []
    for name in ORDERS:
        rec = arms[name] = arm(family, name, r["arms"][name], policy, end, build, r["sealed"])
        all_rows.extend(rec["priced_rows"])
        st = rec["grade"]["measurements"]["FILE"]
        rec["classlru"] = {}
        for size in (161, 288):
            for phase, n, d in (("T2_through_first_final", 10, 1), ("T2_decode", 47, 6)):
                hist = phases[f"classlru_{size}"][phase]
                need(hist["payload_B"] == hist["fills"] * B, "trace bytes")
                rec["classlru"][f"{size}_{phase}"] = price(
                    hist["fills"], n, d, st["median_ns"], st["total_wall_ns"], 5
                )
    pooled = {}
    for mode in G["MODES"]:
        rows = [x for x in all_rows if x["mode"] == mode]
        clocks = {k: sum(x[k] for x in rows) for k in ("wall_ns", "submit_ns", "drain_ns")}
        pooled[mode] = dict(
            n=len(rows),
            total_B=len(rows) * B,
            **clocks,
            aggregate_B_s=len(rows) * B * 10**9 // clocks["wall_ns"],
            median_ns=median(x["wall_ns"] for x in rows),
        )
    return dict(
        status="REPRODUCED_HOT_SHMEM_TO_IK_CUDA",
        family_sha256=a.family_sha256,
        prepared_sha256=a.prepared_sha256,
        source_sha256=build["source_sha256"],
        parent_classlru_sha256=REPLAY,
        inputs=ident,
        arms=arms,
        pooled=pooled,
        payload_B=B,
        scope_peak_bytes=r["max_scope_bytes"],
        swap_peak_bytes=0,
        model_loads=0,
        energy_j=None,
        reviewer_sha256=digest(HERE / "review.py"),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("family", "build", "c55", "prepared", "new-output-dir"):
        p.add_argument("--" + field, type=Path, required=True)
    for field in ("family-sha256", "prepared-sha256"):
        p.add_argument("--" + field, required=True)
    args = p.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    out = args.new_output_dir / "receipt.json"
    try:
        report = review(args)
    except Exception as exc:
        out.write_text(json.dumps(dict(status="FAIL_PRESERVED", reason=str(exc))) + "\n")
        raise
    out.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(report["status"], digest(out))
