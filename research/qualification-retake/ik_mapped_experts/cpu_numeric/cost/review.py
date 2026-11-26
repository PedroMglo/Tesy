"""Review a closed ik CPU receipt without opening any model or polling the host."""

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "admission"))
import authority as auth  # noqa: E402

need = auth.need
PHASES = ("load", "context", "prefill", "teacher", "cleanup")
STAT_GAUGES = ("anon", "file", "file_mapped", "shmem")
COUNTERS = (
    "pgfault",
    "pgmajfault",
    "workingset_refault_file",
    "workingset_activate_file",
    "pgscan",
    "pgsteal",
    "pgscan_direct",
    "pgsteal_direct",
    "pgscan_kswapd",
    "pgsteal_kswapd",
)
READ_KEYS = ("rbytes", "rios", "wbytes", "wios", "dbytes", "dios")


def positive_number(x):
    return type(x) in (float, int) and x >= 0 and math.isfinite(x)


def phases(stdout, saved, successful, supervisor_s):
    marks = {}
    names = []
    for line in stdout.splitlines():
        if not line.startswith("PHASE "):
            continue
        match = re.fullmatch(r"PHASE (\w+) ([0-9]+)", line)
        need(match is not None and match[1] not in marks, "duplicate or unreadable phase")
        names.append(match[1])
        marks[match[1]] = int(match[2])
    need(
        all(
            b > a for a, b in zip(list(marks.values())[:-1], list(marks.values())[1:], strict=True)
        ),
        "clock regression",
    )
    nominal = [phase + suffix for phase in PHASES for suffix in ("_begin", "_end")]
    if successful or saved is not None:
        need(names == nominal and saved == marks, "reported complete native chronology")
    else:
        # A C++ exception or a numerical stop can enter its destructor after any open phase.
        if "cleanup_begin" in names:
            cut = names.index("cleanup_begin")
            need(
                names[:cut] == nominal[:cut] and names[cut:] in (["cleanup_begin"], nominal[-2:]),
                "invalid interrupted phase suffix",
            )
        else:
            need(names == nominal[: len(names)], "invalid prefix")
    durations = {}
    for name in PHASES:
        start, end = (marks.get(name + edge) for edge in ("_begin", "_end"))
        durations[name] = {
            "state": "CLOSED"
            if end is not None
            else "CENSORED"
            if start is not None
            else "UNOBSERVED",
            "seconds": None if end is None else (end - start) / 1e9,
        }
    span = None if len(marks) < 2 else (max(marks.values()) - min(marks.values())) / 1e9
    if supervisor_s is not None:
        need(
            positive_number(supervisor_s) and (span is None or span <= supervisor_s + 1e-9),
            "supervisor elapsed",
        )
    return {
        "native_intervals": durations,
        "native_first_to_last_marker_s": span,
        "native_marks": names,
        "spawn_to_observed_exit_s": supervisor_s,
        "supervisor_cleanup_s": None,
        "scope_exit_s": None,
    }


def sampled(values):
    return {
        "first": values[0] if values else None,
        "last": values[-1] if values else None,
        "max_sampled": max(values, default=None),
    }


def counter(values, endpoint):
    vals = values + ([endpoint] if endpoint is not None else [])
    need(all(type(x) is int and x >= 0 for x in vals), "invalid counter")
    need(all(b >= a for a, b in zip(vals[:-1], vals[1:], strict=True)), "counter regression")
    return {
        "first_sample": values[0] if values else None,
        "last_sample": values[-1] if values else None,
        "post_child": endpoint,
        "first_sample_to_post_child": endpoint - values[0]
        if values and endpoint is not None
        else None,
    }


def resources(rows, end, terminal):
    samples = [row["cgroup"] for row in rows]
    gauges = {}
    for name in ("memory_current", "memory_peak", "swap_current", *STAT_GAUGES):

        def read_value(cg, key=name):
            return (cg["memory_stat"] if key in STAT_GAUGES else cg)[key]

        vals = [read_value(cg) for cg in samples]
        endpoint = None if end is None else read_value(end)
        need(
            all(
                type(v) is int and v >= 0
                for v in vals + ([endpoint] if endpoint is not None else [])
            ),
            "gauge",
        )
        gauges[name] = sampled(vals) | {"post_child": endpoint}
    if end is not None:
        need(all(state["path"] == end["path"] for state in samples), "changing cgroup")
        need(
            end["memory_peak"] >= max((cg["memory_current"] for cg in samples + [end]), default=0),
            "scope peak",
        )
    reclaim = {
        k: counter([cg["memory_stat"][k] for cg in samples], end["memory_stat"][k] if end else None)
        for k in COUNTERS
        if all(k in cg["memory_stat"] for cg in samples + ([end] if end else []))
    }
    psi = {}
    for name in ("some", "full"):
        vectors = [v["pressure"][name] for v in samples]
        final = end["pressure"][name] if end else None
        psi[name] = {
            "total_us": counter([v["total"] for v in vectors], final["total"] if final else None),
            "avg10_pct": sampled([v["avg10"] for v in vectors])
            | {"post_child": final["avg10"] if final else None},
        }
    keys = sorted({k for cg in samples + ([end] if end else []) for k in cg["events"]})
    events = {
        k: counter([cg["events"][k] for cg in samples], end["events"][k] if end else None)
        for k in keys
    }
    timestamps = [v["elapsed_s"] for v in rows]
    need(
        all(positive_number(t) for t in timestamps)
        and all(b > a for a, b in zip(timestamps[:-1], timestamps[1:], strict=True)),
        "runtime monitor order",
    )
    if terminal.get("samples") is not None:
        need(terminal["samples"] == len(rows), "sample count")
    seconds = terminal.get("elapsed_s")
    if timestamps and seconds is not None:
        need(timestamps[-1] <= seconds, "monitor beyond exit")
    devices = terminal.get("io_by_device")
    for source in [v["io"] for v in rows] + ([devices] if devices is not None else []):
        for dev, counts in source.items():
            need(
                re.fullmatch(r"[0-9]+:[0-9]+", dev)
                and all(type(v) is int and v >= 0 for v in counts.values()),
                "io.stat",
            )
    observed = {}
    for dev in sorted({k for row in rows for k in row["io"]}):
        states = [row["io"].get(dev) for row in rows]
        seen = [s for s in states if s is not None]
        observed[dev] = {
            "first_observed": {k: seen[0][k] for k in READ_KEYS if k in seen[0]},
            "last_observed": {k: seen[-1][k] for k in READ_KEYS if k in seen[-1]},
            "samples_with_device": len(seen),
        }
    sector = [r["disk_read_sectors"] for r in rows]
    counter(sector, None)
    disk_bytes = terminal.get("namespace_read_bytes")
    need(
        disk_bytes is None or type(disk_bytes) is int and disk_bytes >= 0 and disk_bytes % 512 == 0,
        "namespace delta",
    )
    if sector and disk_bytes is not None:
        need((sector[-1] - sector[0]) * 512 <= disk_bytes, "namespace coverage")
    return {
        "runtime_samples": len(rows),
        "first_sample_s": timestamps[0] if rows else None,
        "last_sample_s": timestamps[-1] if rows else None,
        "sample_span_s": timestamps[-1] - timestamps[0] if len(rows) >= 2 else None,
        "longest_interior_gap_s": max(
            (b - a for a, b in zip(timestamps[:-1], timestamps[1:], strict=True)), default=None
        ),
        "last_sample_to_observed_exit_s": seconds - timestamps[-1]
        if timestamps and seconds is not None
        else None,
        "gauge_bytes": gauges,
        "kernel_memory_peak_bytes": end["memory_peak"] if end else None,
        "swap_peak_bytes": terminal.get("swap_peak"),
        "memory_stat_counters": reclaim,
        "memory_events": events,
        "cgroup_memory_psi": psi,
        "host_memory_psi_full_avg10_pct": sampled(
            [r["resource_observation"]["host_psi_full_avg10"] for r in rows]
        ),
        "process_sampled_bytes": {
            k: sampled([r[group][k] for r in rows if k in r[group]])
            for group, keys in (
                ("proc", ("VmRSS", "VmHWM", "VmSize", "VmPeak", "VmSwap", "read_bytes")),
                ("smaps", ("Pss", "Pss_Anon", "Pss_File")),
            )
            for k in keys
        },
        "cgroup_io_observed": observed,
        "cgroup_io_before_spawn_to_post_child": devices,
        "namespace": terminal.get("namespace"),
        "namespace_sector_bytes": 512,
        "namespace_rbytes_before_spawn_to_post_child": disk_bytes,
        "namespace_rbytes_first_to_last_sample": (sector[-1] - sector[0]) * 512
        if len(sector) >= 2
        else None,
    }


def original_files(base, inventory, *, limit):
    need(not base.is_symlink(), "linked raw directory")
    if not base.exists():
        need(not inventory, "missing members")
        return
    entries = list(base.iterdir())
    need({p.name for p in entries} == set(inventory), "manifest member set")
    size = 0
    for p in entries:
        need(not p.is_symlink() and p.is_file(), "unsealed member")
        size += p.stat().st_size
        need(size <= limit and auth.sha(p) == inventory[p.name], "raw identity")


def audit(base, expected):
    r = auth.receipt(base / "receipt.json", expected)
    need(
        r["arm"] in ("D0", "D1") and r["status"] in ("PASS_IK_CPU_NUMERIC_ARM", "FAIL_PRESERVED"),
        "terminal arm",
    )
    need(
        r["model_starts"] in (0, 1) and (r["status"] == "FAIL_PRESERVED" or r["model_starts"] == 1),
        "launch count",
    )
    if r["status"] == "PASS_IK_CPU_NUMERIC_ARM":
        need(
            r.get("child_gone") is True
            and r.get("returncode") == 0
            and set(r["logits_sha256"]) == set(auth.NAMES),
            "successful arm endpoints",
        )
    raw, cap = base / "raw", base / "capture"
    original_files(raw, r["raw_sha256"], limit=64 << 20)
    original_files(cap, r["logits_sha256"], limit=2 * auth.ROW)
    need(set(r["logits_sha256"]) <= set(auth.NAMES), "unexpected capture")
    for name in r["logits_sha256"]:
        need((cap / name).stat().st_size == auth.ROW, "invalid row extent")
    if (base / "ids.i32").exists() or r["model_starts"]:
        need(auth.sha(base / "ids.i32") == auth.PACK17 == r["input_sha256"], "teacher input")
    if "source_sha256" in r:
        expected_sources = r["source_sha256"] | {"protocol.md": r["protocol_sha256"]}
        need(
            set(expected_sources) == {"authority.py", "profile.py", "protocol.md"},
            "supervisor source set",
        )
        for filename, digest in expected_sources.items():
            path = auth.HERE / filename
            if auth.sha(path) != digest:
                rev = r.get("commit", "")
                need(re.fullmatch("[0-9a-f]{40}", rev), "producer revision")
                blob = subprocess.check_output(
                    ["git", "-C", auth.ROOT, "show", rev + ":" + str(path.relative_to(auth.ROOT))]
                )
                need(auth.digest(blob) == digest, "historical supervisor source")
    if r["model_starts"]:
        need(
            r["placement_sha256"] == auth.PLACEMENT
            and r["model_sha256"] == auth.stock.MODEL_SHA
            and r["gold_sha256"] == dict(zip(auth.NAMES, auth.GOLD, strict=True)),
            "model/gold authority",
        )
        for name, digest in auth.LIBS.items():
            need(r["providers"][Path(name).name]["sha256"] == digest, "ELF providers")
    inv = r.get("c118")
    c118 = None
    if inv:
        name = inv["run_id"] + ".start-inventory.jsonl"
        need(inv["sha256"] == r["raw_sha256"][name], "C118 hash")
        lines = [json.loads(line) for line in (raw / name).read_text().splitlines()]
        need(
            len(lines) == inv["sample_count"]
            and lines[-1]["utc"] == inv["last_utc"]
            and len(lines) >= 61,
            "C118 coverage",
        )
        need(
            lines[-1]["elapsed_s"] == inv["duration_s"]
            and inv["duration_s"] >= 60
            and inv["run_id"] == r.get("unit", inv["run_id"]),
            "C118 times and identity",
        )
        c118 = {"samples": len(lines), "seconds": inv["duration_s"], "sha256": inv["sha256"]}
    data = {}
    for f in ("native.stdout", "native.stderr", "monitor.jsonl"):
        data[f] = (raw / f).read_text() if f in r["raw_sha256"] else ""
    terminal = re.findall(r"^STATUS (\w+)$", data["native.stdout"], re.M)
    need(terminal == r.get("native_status", []), "native status mismatch")
    rows = [json.loads(line) for line in data["monitor.jsonl"].splitlines()]
    times = phases(
        data["native.stdout"],
        r.get("phase_monotonic_ns"),
        r["status"].startswith("PASS"),
        r.get("elapsed_s"),
    )
    if r.get("unit"):
        for cg in [row["cgroup"] for row in rows] + (
            [r["cgroup_end"]] if r.get("cgroup_end") else []
        ):
            need(
                Path(cg["path"]).name == r["unit"] + ".scope"
                and cg["memory_max"] == r["envelope_gib"] * (1 << 30),
                "runtime scope identity",
            )
    timing = resources(rows, r.get("cgroup_end"), r)
    why = r.get("reason", "")
    error = re.fullmatch(r"ValueError: (native rc -?\d+ \[.*?\]|[A-Z][A-Z_\d]+)", why)
    vma = re.findall(
        r"^non-file or writable view (blk\.\d+\.ffn_(?:gate|up|down)_exps\.(?:weight|bias))$",
        data["native.stderr"],
        re.M,
    )
    need(len(vma) <= 1, "ambiguous VMA diagnostic")
    return {
        "status": "REPRODUCED_CLOSED_ARM_COSTS",
        "arm": r["arm"],
        "arm_status": r["status"],
        "reason_category": (
            "NATIVE_EXIT" if error and error[1].startswith("native rc") else error[1]
        )
        if error
        else None,
        "vma_mismatch_tensor": vma[0] if vma else None,
        "terminal_sha256": expected,
        "protocol_sha256": auth.sha(HERE / "protocol.md"),
        "reviewer_sha256": auth.sha(Path(__file__)),
        "producer_commit": r.get("commit"),
        "build_sha256": r.get("build_sha256"),
        "c55_sha256": r.get("c55_sha256"),
        "c118": c118,
        "runtime_monitor_sha256": r["raw_sha256"].get("monitor.jsonl"),
        "model_starts": r["model_starts"],
        "returncode": r.get("returncode"),
        "child_gone": r.get("child_gone"),
        "native_status": terminal,
        "captured_rows": sorted(r["logits_sha256"]),
        "scope_limits_bytes": {
            k: r.get("cgroup_end", {}).get(k) for k in ("memory_max", "memory_high", "swap_max")
        },
        "native_cleanup_closed": times["native_intervals"]["cleanup"]["state"] == "CLOSED",
        "runtime": times,
        "resources": timing,
        "energy_j": None,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--arm-dir", type=Path, required=True)
    p.add_argument("--receipt-sha256", required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = audit(a.arm_dir, a.receipt_sha256)
    except (OSError, ValueError, KeyError, TypeError, IndexError, RuntimeError) as exc:
        result = {
            "status": "FAIL_COST_REVIEW",
            "exception": type(exc).__name__,
            "terminal_sha256": a.receipt_sha256,
        }
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(result["status"])
    return int(result["status"] == "FAIL_COST_REVIEW")


if __name__ == "__main__":
    raise SystemExit(main())
