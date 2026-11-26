"""Run one pre-registered four-arm copy operator on the reference laptop."""

import argparse
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(str(HERE.parent / "slots.py"))
G, need, sha, save = (S[k] for k in ("G", "need", "sha", "save"))
OPERATOR = run_path(str(HERE / "copy_operator.py"))
W = run_path(str(G["REPO"] / "research/qualification-retake/nvme_admission/window.py"))
inv = W["inv"]
METHOD = "b7807cac36a9514df15d366a5e048fea141d24351f794afd65894f8bad0facbc"
SLOTS = "7d3e20f41f8e1c92add2e7bad358a1c61026950f2c145567f496c179d97c8063"
WINDOW = "41e3143815799044c50b2756475b14252603c87be68c43952a4225ef94165d3c"
PINS = {
    "/usr/bin/python3": "44580a031f15af0c03db8f84299b1da4f9740df4467e30cf30bc2143084cf500",
    "/usr/lib64/libc.so.6": "a5c5ad9d59d3c69eda93aa8f82930ba06cc4e893a113e66c85ad6e96243d53c8",
    OPERATOR["DRIVER"]: "33d4cbb6bc86ccc76c1e60af3b83c316ea49d7cb311efa79efc8ade96114cd8e",
}


def energy():
    readings = {}
    for domain in Path("/sys/class/powercap").glob("*:*"):
        try:
            readings[domain.name] = dict(
                uj=int((domain / "energy_uj").read_text()),
                max_uj=int((domain / "max_energy_range_uj").read_text()),
            )
        except (PermissionError, FileNotFoundError):
            continue
    return readings


def mappings():
    files = set()
    for line in Path("/proc/self/maps").read_text().splitlines():
        f = line.split(maxsplit=5)
        if len(f) == 6 and "x" in f[1] and f[5].startswith("/"):
            files.add(Path(f[5]).resolve(strict=True))
    need({Path(k).resolve() for k in PINS} <= files, "loaded Python, libc and driver")
    return {str(p): sha(p) for p in sorted(files)}


def sample(policy, unit, active):
    now = datetime.now(UTC)
    need(
        0 <= (now - datetime.fromisoformat(policy["snapshot"]["utc"])).total_seconds() < 3600,
        "C55 age",
    )
    group = Path("/proc/self/cgroup").read_text().strip().split("::", 1)[1]
    need(group.endswith("/" + unit + ".service"), "dedicated service")
    root = Path("/sys/fs/cgroup") / group.lstrip("/")
    names = ("memory.high", "memory.max", "memory.peak", "memory.swap.max", "memory.swap.current")
    limits = {k: int((root / k).read_text()) for k in names}
    events = dict(line.split() for line in (root / "memory.events").read_text().splitlines())
    need(
        limits["memory.max"] == limits["memory.high"] == 4 << 30
        and 0 < limits["memory.peak"] < 4 << 30
        and limits["memory.swap.max"] == limits["memory.swap.current"] == 0
        and all(int(events[k]) == 0 for k in ("max", "oom", "oom_kill")),
        "RAM/swap/cgroup",
    )
    gpu = W["parse_gpu_csv"](
        inv.call(
            "nvidia-smi",
            "--query-gpu=uuid,pci.bus_id,name,memory.total,memory.used,temperature.gpu,driver_version",
            "--format=csv,noheader,nounits",
        )
    )
    owners = set(
        inv.call(
            "nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"
        ).splitlines()
    )
    need(owners <= ({str(os.getpid())} if active else set()), "concurrent GPU process")
    mem, power, psi = inv.memory(), inv.power(), inv.psi()["avg10"]
    sensor = json.loads(inv.call("sensors", "-j"))
    cpu = sensor[policy["cpu"]["sensor"]]["Tctl"]["temp1_input"]
    disk = {p["sensor"]: sensor[p["sensor"]]["Composite"]["temp1_input"] for p in policy["nvme"]}
    need(
        power["source"] == "AC"
        and power["profile"] == "performance"
        and power["online_sources"] == policy["power"]["online_sources"]
        and psi < 10
        and mem["MemAvailable"] >= (4 << 30) + policy["memory"]["reserve_bytes"],
        "power/pressure/available memory",
    )
    need(
        gpu["uuid"] == policy["gpu"]["uuid"]
        and gpu["driver"] == policy["gpu"]["driver"]
        and gpu["used_mib"] < policy["gpu"]["memory_stop_total_mib"]
        and gpu["temperature_c"] < policy["gpu"]["warning_c"]
        and cpu < policy["cpu"]["warning_c"]
        and all(disk[k["sensor"]] < min(k["stop_c"], k["warning_c"]) for k in policy["nvme"]),
        "thermal or GPU limits",
    )
    return dict(
        utc=now.isoformat(),
        gpu=gpu,
        compute_owners=sorted(owners),
        cpu_c=cpu,
        nvme_c=disk,
        limits=limits,
        memory=mem,
        power=power,
        psi_full_avg10=psi,
        energy=energy(),
    )


def run(a, out, r):
    head, tree = G["tree"](G["REPO"])
    need(
        head == a.commit
        and sha(HERE / "protocol.md") == METHOD
        and Path("/proc/self/exe").resolve() == Path("/usr/bin/python3").resolve(),
        "frozen sources",
    )
    need(all(sha(Path(k)) == v for k, v in PINS.items()), "native provider pins")
    r.update(
        commit=head,
        tree=tree,
        program_sha256=sha(Path(__file__)),
        operator_sha256=sha(HERE / "copy_operator.py"),
        provider_pins=PINS,
        fixture="dense aligned-size components, separate chain per rescue",
    )
    window = G["read"](a.window / "receipt.json", WINDOW)
    policy = G["read"](a.window / "resource-policy.json", window["canonical_policy_sha256"])
    need(
        window["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and not window["reason"]
        and sha(a.window / "samples.jsonl") == window["window_sha256"]
        and "HX 370" in window["cpu"]
        and "4060 Laptop" in window["gpu_name"]
        and window["model_bytes_read"] == 0,
        "physical window",
    )
    rec = G["read"](a.schedule / "result.json", SLOTS)
    plan = rec["matched"]["schedule"]
    need(
        len(plan) == 35
        and sum(row["source"][0] < 25 for row in plan) == 21
        and rec["two_physical_copies_payload_bytes"] == 6 * OPERATOR["SLAB"] * len(plan),
        "physical operator counts",
    )
    records = []

    def observe(stage, active):
        row = sample(policy, a.unit, active)
        save(out / (stage + ".json"), row)
        records.append(row)

    observe("before", False)
    gpu = OPERATOR["Cuda"]()
    try:
        buffers = OPERATOR["Transfers"](plan, gpu)
        r.update(
            cuda_driver_api=gpu.version.value,
            explicit_device_B=len(gpu.allocations) * OPERATOR["SLAB"],
            explicit_host_component_B=len(buffers.host) * OPERATOR["SLAB"],
            observed_executable_files=mappings(),
        )
        parts = [p.sha256 for _, row in buffers.components for p in row]
        experts = {(item["source"][0], item["source"][3]) for item in plan}
        need(len(parts) == 105 and len(set(parts)) == 3 * len(experts), "component identities")
        r["expected_digest"] = hashlib.sha256("".join(parts).encode()).hexdigest()
        observe("allocated", True)
        for mode in "AB":
            buffers.reset()
            buffers.timed(mode)
            need(not buffers.different(), "wrong warmup destination")
        bad = buffers.corrupt()
        need(buffers.different() == [bad], "missed one-byte corruption")
        r.update(exact_components_per_arm=105, one_byte_negative=list(bad))
        for index, mode in enumerate(a.order):
            buffers.reset()
            observe(f"arm-{index}-start", True)
            row = buffers.timed(mode)
            need(not buffers.different(), "wrong timed destination")
            observe(f"arm-{index}-end", True)
            save(out / f"arm-{index}.json", row)
            r["arms"].append(row)
    finally:
        gpu.close()
    observe("cleanup", True)
    r.update(
        peak_cgroup_B=max(v["limits"]["memory.peak"] for v in records),
        maximum_gpu_used_MiB=max(v["gpu"]["used_mib"] for v in records),
        maximum_cpu_c=max(v["cpu_c"] for v in records),
        maximum_gpu_c=max(v["gpu"]["temperature_c"] for v in records),
        energy_first=records[0]["energy"],
        energy_last=records[-1]["energy"],
    )
    return "PASS_PAIRED_COPY_OPERATOR"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("window", "schedule", "new-output-dir"):
        p.add_argument("--" + k, required=True, type=Path)
    for k in ("commit", "unit"):
        p.add_argument("--" + k, required=True)
    p.add_argument("--order", choices=("ABBA", "BAAB"), required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    start = time.monotonic()
    r = dict(
        status="FAIL_PRESERVED",
        protocol_sha256=METHOD,
        schedule_sha256=SLOTS,
        window_sha256=WINDOW,
        unit=a.unit,
        order=a.order,
        arms=[],
        model_starts=0,
        requests=0,
    )
    try:
        r["status"] = run(a, a.new_output_dir, r)
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
    r["wall_s"] = time.monotonic() - start
    save(a.new_output_dir / "result.json", r)
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
