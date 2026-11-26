"""Compare complete CPU attention outputs in two independent, bounded native processes."""

import argparse
import math
import os
import platform
import re
import struct
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
B = run_path(str(HERE / "build.py"))
F, G, need, sha, save = (B[k] for k in ("F", "G", "need", "sha", "save"))
BUILD = "b02c9de04b5c37497760575194e5ba61589ee037ffcddce898f5e0c5083d35f0"
WINDOW = "ad8c82c323975f8ef31d68ae7d66a26b7de9c154f29a0d20aa405482428e9cc7"
CASES = [(n, span) for n in B["CASES"] for span in (0, 128)]


def outputs(folder):
    rows = {}
    hashes = {}
    for n, span in CASES:
        key = f"{n}-{span}"
        base = folder / key
        ref = (base / "serial.f32").read_bytes()
        need(len(ref) == 3 * 4096 * 4, "output geometry")
        row = {}
        for op in ("serial", "block", "rows", "wrong"):
            p = base / (op + ".f32")
            data = p.read_bytes()
            need(
                len(data) == len(ref)
                and all(math.isfinite(f) for (f,) in struct.iter_unpack("<f", data)),
                "finite complete output",
            )
            hashes[key + "/" + p.name] = sha(p)
            if op != "serial":
                row[op] = [
                    sum(
                        a != b
                        for a, b in zip(
                            struct.iter_unpack("<I", ref[j : j + 16384]),
                            struct.iter_unpack("<I", data[j : j + 16384]),
                            strict=True,
                        )
                    )
                    for j in range(0, len(ref), 16384)
                ]
        rows[key] = row
    passed = all(
        v["rows"] == [0, 0, 0] and v["wrong"][0] and v["wrong"][2] and not v["wrong"][1]
        for v in rows.values()
    )
    passed = (
        passed
        and all(not any(rows[f"256-{s}"]["block"]) for s in (0, 128))
        and any(rows["2304-128"]["block"])
    )
    return dict(passed=bool(passed), different_F32_by_position=rows, vectors=hashes)


def resource(p, unit):
    lines = p.read_text().splitlines()
    need(
        lines[0].endswith("/" + unit + ".service")
        and lines[1:5] == ["memory.max", str(2 << 30), "memory.swap.max", "0"]
        and lines[5] == "memory.peak"
        and lines[7:10] == ["memory.swap.current", "0", "memory.events"],
        "scope caps and swap",
    )
    events = dict(x.split() for x in lines[10:])
    need(all(int(events[k]) == 0 for k in ("max", "oom", "oom_kill")), "scope events")
    return int(lines[6])


def native(folder, unit, built, exe):
    f = folder / "vectors"
    paths = {
        row.split(None, 5)[5]
        for row in (f / "maps").read_text().splitlines()
        if len(row.split(None, 5)) == 6 and row.split(None, 5)[5].startswith("/")
    }
    libs = {p for p in paths if ".so" in Path(p).name}
    need(
        {d["file"] for d in built["providers"].values()} == libs and str(exe) in paths,
        "mapped CPU ELF closure",
    )
    start = resource(f / "start.resource", unit)
    end = resource(f / "end.resource", unit)
    need(0 < start <= end <= 2 << 30, "cgroup peak")
    return dict(peak_B=end, providers=len(libs), **outputs(f))


def host(stage):
    state = dict(
        kernel=platform.release(),
        machine=platform.machine(),
        utc=datetime.now(UTC).isoformat(),
        stage=stage,
    )
    for name, cmd in {
        "cpu": ["/usr/bin/lscpu", "-J"],
        "gpu": [
            "/usr/bin/nvidia-smi",
            "--query-gpu=name,driver_version,memory.total,memory.used,temperature.gpu,power.draw",
            "--format=csv,noheader,nounits",
        ],
        "compute_owners": [
            "/usr/bin/nvidia-smi",
            "--query-compute-apps=pid",
            "--format=csv,noheader,nounits",
        ],
        "memory": ["/usr/bin/free", "-b"],
        "power": ["/usr/bin/powerprofilesctl", "get"],
    }.items():
        state[name] = subprocess.check_output(cmd, text=True, timeout=8).strip()
    need(
        "HX 370" in state["cpu"]
        and "4060 Laptop" in state["gpu"]
        and not state["compute_owners"]
        and state["power"] == "performance",
        "reference host and idle GPU",
    )
    return state


def run(a, out, r):
    head, tree = G["tree"](G["REPO"])
    need(
        head == a.commit
        and sha(HERE / "protocol.md") == B["METHOD"]
        and re.fullmatch(r"tesy-cpu-attention-[a-z0-9-]+", a.unit),
        "source or unit",
    )
    r.update(commit=head, tree=tree)
    built = G["read"](a.build / "receipt.json", BUILD)
    need(
        built["status"] == "GO_CPU_FIXTURE_BUILD"
        and all(sha(a.build / k) == h for k, h in built["files"].items()),
        "CPU binary and build",
    )
    need(
        all(sha(Path(k["file"])) == k["sha256"] for k in built["providers"].values()),
        "providers on disk",
    )
    window = G["read"](a.window / "receipt.json", WINDOW)
    policy = G["read"](a.window / "resource-policy.json", window["canonical_policy_sha256"])
    F["S"]["PK"]["PK"]["age"](policy, datetime.now(UTC))
    need(
        window["status"] == "PASS_RESOURCE_WINDOW_ONLY"
        and sha(a.window / "samples.jsonl") == window["window_sha256"],
        "C55",
    )
    save(out / "before.json", host("before"))
    exe = a.build / "cpu-fixture"
    lib = str(Path(built["providers"]["libggml-cpu.so.0"]["file"]).parent)
    for i in (1, 2):
        key = str(i)
        unit = a.unit + "-" + key
        folder = out / key
        folder.mkdir()
        cmd = [
            "systemd-run",
            "--user",
            "--wait",
            "--collect",
            "--pipe",
            "--service-type=exec",
            "--unit=" + unit,
            "-p",
            "MemoryMax=2G",
            "-p",
            "MemorySwapMax=0",
            "-p",
            "RuntimeMaxSec=45",
            "-p",
            "LimitCORE=0",
            "-p",
            "CoredumpFilter=0x0",
            "--",
            "/usr/bin/env",
            "-i",
            "LANG=C",
            "PATH=/usr/bin",
            "OMP_NUM_THREADS=8",
            "LD_LIBRARY_PATH=" + lib,
            str(exe),
            str(folder / "vectors"),
        ]
        save(folder / "argv.json", cmd)
        start = time.monotonic()
        with (folder / "scope.log").open("xb") as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=55)
        item = native(folder, unit, built, exe)
        r["arms"][key] = dict(wall_s=time.monotonic() - start, **item)
        need(item["passed"], "operator prediction failed in run " + key)
    need(r["arms"]["1"]["vectors"] == r["arms"]["2"]["vectors"], "independent CPU repeat")
    save(out / "after.json", host("after"))
    return "GO_CPU_ROW_OPERATOR_ONLY"


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("build", "window", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    for k in ("commit", "unit"):
        p.add_argument("--" + k, required=True)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir.resolve()
    out.mkdir()
    t = time.monotonic()
    r = dict(
        status="FAIL_PRESERVED",
        protocol_sha256=B["METHOD"],
        build_sha256=BUILD,
        window_sha256=WINDOW,
        unit=a.unit,
        arms={},
    )
    try:
        r["status"] = run(a, out, r)
    except Exception as exc:
        r["error"] = f"{type(exc).__name__}: {exc}"
    r.update(
        wall_s=time.monotonic() - t,
        model_starts=0,
        files={str(k.relative_to(out)): sha(k) for k in sorted(out.rglob("*")) if k.is_file()},
    )
    save(out / "receipt.json", r)
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
