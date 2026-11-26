"""Passively evaluate R0's frozen cap for a new NVMe copy. No weight FD or server."""

import argparse
import json
import os
import re
import signal
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "tools"))
import c55_inventory as inv  # noqa: E402
from c143_slots40_optin import MODEL  # noqa: E402
from host_resource_policy import (  # noqa: E402
    GIB,
    derive_policy,
    operational_session_ready,
    parse_gpu_csv,
)
from run_bounded import sha256  # noqa: E402


def save(path, obj):
    with path.open("x") as f:
        json.dump(obj, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


def stat_id(path):
    st = path.stat()
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def mount(path):
    return inv.call(
        "findmnt", "--first-only", "-T", str(path.resolve()), "-no", "SOURCE,FSTYPE"
    ).split()


def concurrent():
    active = set()
    for comm in Path("/proc").glob("[0-9]*/comm"):
        try:
            name = comm.read_text().strip()
            if name in {
                "cc1",
                "cc1plus",
                "ptxas",
                "cicc",
                "nvcc",
                "ld",
                "ld.lld",
                "ninja",
                "llama-server",
                "llama-bench",
                "llama-cli",
                "block-prefill-re",
            }:
                active.add(name)
            if name in {"cp", "dd", "rsync", "sha256sum", "b2sum", "python3", "python"}:
                argv = (comm.parent / "cmdline").read_bytes().split(b"\x00")
                if name in {"cp", "dd", "rsync", "sha256sum", "b2sum"} and any(
                    b".gguf" in a for a in argv
                ):
                    active.add("GGUF transfer/hash")
                if name in {"python", "python3"} and any(
                    Path(os.fsdecode(arg)).name in {"transfer.py", "copy_gguf.py", "place.py"}
                    for arg in argv[1:]
                    if arg and not arg.startswith(b"-")
                ):
                    active.add("transfer")
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return sorted(active)


def collect(model, out):
    hist = json.loads(
        (
            REPO / "results/c281-persistent-r0-runtime-20261005/protocols/c281-r0-persistent.json"
        ).read_text()
    )
    old = hist["c120"]["model_stat"]
    selected = model.resolve(strict=True)
    frozen = stat_id(selected)
    if frozen[2] != old["size"]:
        raise ValueError("NVMe target has unexpected size")
    _, devices = inv.mounts({"model": selected})
    source, filesystem = mount(selected)
    disk = re.fullmatch(r"/dev/(nvme\d+n\d+)(?:p\d+)?(?:\[.*\])?", source)
    if not disk or len(devices) != 1:
        raise ValueError("NVMe model transport unresolved")
    logical = Path("/sys/class/block") / disk[1] / "stat"
    unit = inv.call("systemctl", "--user", "show", "app.slice", "-p", "ControlGroup", "--value")
    if not unit.startswith("/user.slice/") or not unit.endswith("/app.slice"):
        raise ValueError("destination app.slice ancestry unresolved")
    cpu = inv.cpu_identity()
    rows = []
    with (out / "samples.jsonl").open("x") as f:
        while True:
            sample_start = time.monotonic()
            mem = inv.memory()
            source_headroom, _ = inv.ancestor_headroom(mem["MemTotal"])
            target_headroom, _ = inv.ancestor_headroom(mem["MemTotal"], rel=unit)
            gpu_csv = inv.call(
                "nvidia-smi",
                "--query-gpu=uuid,pci.bus_id,name,memory.total,memory.used,temperature.gpu,driver_version",
                "--format=csv,noheader,nounits",
            )
            gpu = parse_gpu_csv(gpu_csv)
            apps = inv.call(
                "nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"
            )
            sensors = json.loads(inv.call("sensors", "-j"))
            pwr = inv.power()
            diskstat = [int(v) for v in logical.read_text().split()]
            clocks = time.monotonic()
            if not rows:
                start = clocks
            row = dict(
                elapsed_s=clocks - start,
                utc=datetime.now(UTC).isoformat(),
                mem_available=mem["MemAvailable"],
                swap_free=mem["SwapFree"],
                psi_full=inv.psi()["avg10"],
                ancestor=min(source_headroom, target_headroom),
                cpu_c=next(
                    v["Tctl"]["temp1_input"] for k, v in sensors.items() if k.startswith("k10temp-")
                ),
                nvme_c={
                    k: v["Composite"]["temp1_input"]
                    for k, v in sensors.items()
                    if k.startswith("nvme-pci-")
                },
                gpu_c=gpu["temperature_c"],
                gpu_used=gpu["used_mib"],
                gpu_id=gpu["uuid"],
                gpu_compute_count=len(apps.splitlines()),
                conflicts=concurrent(),
                power=pwr,
                disk_read_sectors=diskstat[2],
                disk_written_sectors=diskstat[6],
                disk_busy_ms=diskstat[9],
            )
            f.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
            f.flush()
            rows.append(row)
            if row["elapsed_s"] >= 60:
                break
            time.sleep(max(0, start + len(rows) - time.monotonic() - (clocks - sample_start)))
    gaps = [b["elapsed_s"] - a["elapsed_s"] for a, b in zip(rows, rows[1:], strict=False)]
    if len(rows) < 61 or min(gaps) <= 0 or max(gaps) > 1.5:
        raise ValueError("60s interval/cadence incomplete")
    if frozen != stat_id(selected) or model.resolve() != selected:
        raise ValueError("NVMe file changed")
    mem.update(
        MemAvailable_min=min(r["mem_available"] for r in rows),
        MemAvailable_max=max(r["mem_available"] for r in rows),
        ancestor_headroom_bytes=min(r["ancestor"] for r in rows),
    )
    # Pair final GPU temperature with the matching contemporaneous threshold query.
    sensor_tm = inv.call("nvidia-smi", "-q", "-d", "TEMPERATURE")
    snap = dict(
        memory=mem,
        gpu_csv=gpu_csv,
        gpu_temperature_query=sensor_tm,
        sensors=sensors,
        cpu_identity=cpu,
        involved_nvme=devices,
        power=pwr,
        psi={"full_avg10": rows[-1]["psi_full"]},
    )
    policy = derive_policy(snapshot=snap)
    reasons = set(operational_session_ready(policy)[1])
    stop = policy["gpu"]["memory_stop_total_mib"]
    for r in rows:
        if (
            r["power"]["source"] != "AC"
            or r["power"]["profile"] != "performance"
            or r["power"]["online_sources"] != pwr["online_sources"]
        ):
            reasons.add("POWER")
        if r["psi_full"] >= 10:
            reasons.add("HOST_PSI_AT_STOP")
        if r["gpu_compute_count"] or r["conflicts"]:
            reasons.add("CONCURRENT_JOB")
        if r["cpu_c"] >= policy["cpu"]["warning_c"] or r["gpu_c"] >= min(
            value
            for value in (policy["gpu"]["stop_c"], policy["gpu"]["warning_c"])
            if value is not None
        ):
            reasons.add("START_TEMPERATURE")
        if r["gpu_id"] != gpu["uuid"] or r["gpu_used"] >= stop:
            reasons.add("GPU_ID_OR_CAP")
        for guard in policy["nvme"]:
            if r["nvme_c"][guard["sensor"]] >= min(
                v for v in (guard["warning_c"], guard["stop_c"]) if v is not None
            ):
                reasons.add("NVME_TEMPERATURE")
    cap = policy["memory"]["cap_max_bytes"]
    if cap < 20 * GIB:
        reasons.add("HOST_CAP_PLUS_RESERVE_UNAVAILABLE")
    old_id = [old[k] for k in ("dev", "ino", "size", "mtime_ns")]
    return dict(
        status="NOT_ADMITTED" if reasons else "PASS_RESOURCE_WINDOW_ONLY",
        r0_launch="NOT_RUN",
        reason=sorted(reasons),
        samples=len(rows),
        span_s=rows[-1]["elapsed_s"],
        max_gap_s=max(gaps),
        window_sha256=sha256(out / "samples.jsonl"),
        model_bytes_read=0,
        historical_stat_equal=(frozen[:4] == old_id),
        selected_stat=frozen,
        historical_path_points_to_selected=MODEL.exists() and MODEL.samefile(selected),
        model_device=source,
        model_fs=filesystem,
        cpu=cpu["model"],
        nvme=policy["nvme"],
        gpu_name=gpu["name"],
        gpu_driver=gpu["driver"],
        gpu_total_mib=gpu["total_mib"],
        gpu_used_mib_max=max(r["gpu_used"] for r in rows),
        gpu_c_max=max(r["gpu_c"] for r in rows),
        cpu_c_max=max(r["cpu_c"] for r in rows),
        nvme_c_max={
            a["sensor"]: max(r["nvme_c"][a["sensor"]] for r in rows) for a in policy["nvme"]
        },
        power=pwr,
        swap_total=mem["SwapTotal"],
        swap_free_min=min(r["swap_free"] for r in rows),
        psi_full_max=max(r["psi_full"] for r in rows),
        memory=policy["memory"],
        r0_cap_bytes=20 * GIB,
        missing_capacity_bytes=max(0, 20 * GIB - cap),
        concurrent=sorted(set(v for r in rows for v in r["conflicts"])),
        gpu_compute_max=max(r["gpu_compute_count"] for r in rows),
        disk_delta={
            k: rows[-1][k] - rows[0][k]
            for k in ("disk_read_sectors", "disk_written_sectors", "disk_busy_ms")
        },
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nvme-model", required=True, type=Path)
    ap.add_argument("--new-output-dir", required=True, type=Path)
    args = ap.parse_args()
    args.new_output_dir.mkdir(mode=0o700)

    def timeout(*_):
        raise TimeoutError("window 100 s limit")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(100)
    try:
        # Preserve the canonical C55 policy and independently witness the same period.
        # C55 has a module-level historical model path; select the real candidate explicitly.
        inv.MODEL = str(args.nvme_model.resolve(strict=True))
        with ThreadPoolExecutor(max_workers=1) as pool:
            canonical = pool.submit(inv.run, args.new_output_dir)
            receipt = collect(args.nvme_model, args.new_output_dir)
            canonical.result()
        canonical_path = args.new_output_dir / "resource-policy.json"
        official = json.loads(canonical_path.read_text())
        if (
            derive_policy(snapshot=json.loads((args.new_output_dir / "snapshot.json").read_text()))
            != official
        ):
            raise ValueError("C55 canonical snapshot and policy disagree")
        receipt["canonical_policy_sha256"] = sha256(canonical_path)
        receipt["canonical_memory"] = official["memory"]
        if (
            official["memory"]["cap_max_bytes"] < 20 * GIB
            and "HOST_CAP_PLUS_RESERVE_UNAVAILABLE" not in receipt["reason"]
        ):
            receipt["reason"].append("C55_CAP_UNAVAILABLE")
            receipt["status"] = "NOT_ADMITTED"
        storage_free = official["snapshot"]["storage_free_bytes"]
        receipt["raw_destination_free_bytes"] = storage_free
        if storage_free < 11 * GIB:
            receipt["reason"].append("RAW_DESTINATION_FREE_BELOW_11_GIB")
            receipt["status"] = "NOT_ADMITTED"
    except Exception as exc:
        receipt = dict(status="FAIL_INVENTORY", r0_launch="NOT_RUN", error=str(exc))
    signal.alarm(0)
    receipt["protocol_sha256"] = sha256(HERE / "protocolo.md")
    receipt["runner_sha256"] = sha256(__file__)
    save(args.new_output_dir / "receipt.json", receipt)
    print(json.dumps(receipt, indent=2))
    sys.exit(receipt["status"] == "FAIL_INVENTORY")
