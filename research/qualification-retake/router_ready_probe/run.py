"""Run the isolated C291 CPU router-to-remap witness without weights."""

import argparse
import hashlib
import importlib.util
import json
import resource
import struct
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LIBS = {
    "libggml-cpu.so.0.15.3": "9aabce5751c5d7ca19b50e4cabb1fcf484c1581d275141dae8aba8ed33060313",
    "libggml-base.so.0.15.3": "6e27d9ecb86e4747177189d2d2f6390280a2ee1000221ad68a0404023ea72539",
}
C269 = "d0ebfbcc6c8f456bc1083027c1b08075a32824d8"
HELPER = "67523bc7c44d6cf1182b45008e7414d160254b62a64c1ffe142fe934ab65509e"
PROTOCOL = "2498c8e6264d69f89dd0aacdea048d2a70b36d57985890ff0a5e95f218477eab"
GRAPH = "d1a2ce42e649305416665091ecee4523c1638721d42cca34b51a03bbcfce3288"
MODES = ("BASE", "OFF", "ON", "WRONG")
MEMORY = 1 << 30
OUTPUT = 64 << 20


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(path):
    with path.open("rb") as reader:
        return hashlib.file_digest(reader, "sha256").hexdigest()


def git(repo, *args):
    return subprocess.check_output(
        [
            "/usr/bin/git",
            "--no-optional-locks",
            "-c",
            "core.preloadIndex=false",
            "-c",
            "index.threads=1",
            "-C",
            repo,
            *args,
        ],
        timeout=10,
    )


def verdict(mode, n, raw, metadata, baseline=None):
    ids = [(row * 5 + rank * 3) % 16 for row in range(n) for rank in range(4)]
    count = len(ids)
    need(len(raw) == 12 * count, "length")
    ranks = struct.unpack_from(f"<{count}i", raw)
    slots = struct.unpack_from(f"<{count}i", raw, 4 * count)
    probabilities = struct.unpack_from(f"<{count}f", raw, 8 * count)
    need(list(ranks) == ids and list(slots) == [(7 * e + 3) % 40 for e in ids], "ranks or slots")
    need(all(0 < v < 1 for v in probabilities), "weights")
    need(
        all(abs(sum(probabilities[p : p + 4]) - 1) < 0.000001 for p in range(0, count, 4)),
        "softmax",
    )
    need(
        metadata["mode"] == mode and metadata["rows"] == n and metadata["hits"] == len(set(ids)),
        "run identity",
    )
    need(metadata["splits"] == 1 and metadata["graph"].split(",").count("GET_ROWS") == 1, "graph")
    if baseline:
        need(raw == baseline[0] and metadata["graph"] == baseline[1], "ablation output or topology")
    hooked = int(mode != "BASE")
    for k in ("entries", "forwarded", "remaps"):
        need(metadata[k] == hooked, "missing or repeated interception")
    need((1 <= metadata["threads"] <= 8) if hooked else metadata["threads"] == 0, "compute threads")
    start, ready, end = (metadata[k] for k in ("start", "ready", "consumer"))
    resolution, tick = metadata["resolution"], metadata["min_tick"]
    need(resolution > 0 and tick > 0, "clock calibration")
    if mode in ("ON", "WRONG"):
        need(0 < start <= ready <= end, "clocks")
        need(
            (metadata["different"] > 0) if mode == "WRONG" else metadata["different"] == 0,
            "stride negative",
        )
        return {
            "entry_to_remap_ns": end - start,
            "copy_ns": ready - start,
            "ready_to_remap_ns": end - ready,
            "resolved": end - ready > max(resolution, tick),
        }
    need(start == ready == end == metadata["different"] == 0, "unexpected disabled observation")
    return None


def scope(unit):
    entry = Path("/proc/self/cgroup").read_text().splitlines()
    need(len(entry) == 1 and entry[0].startswith("0::/"), "cgroup v2")
    parts = Path(entry[0][3:])
    need(parts.name == unit + ".scope", "dedicated scope")
    cg = Path("/sys/fs/cgroup") / parts.relative_to("/")
    need(
        int((cg / "memory.max").read_text()) == MEMORY
        and int((cg / "memory.swap.max").read_text()) == 0,
        "scope caps",
    )
    return cg


def run(args, receipt):
    out = args.new_output_dir.resolve(strict=True)
    cg = scope(args.unit)
    events0 = (cg / "memory.events").read_text()
    need(sha(HERE / "protocol.md") == PROTOCOL, "protocol")
    head = git(ROOT, "rev-parse", "HEAD").decode().strip()
    need(head == args.commit and not git(ROOT, "status", "--porcelain"), "freeze")
    helpers = HERE.parent / "packed_worker" / "run.py"
    need(sha(helpers) == HELPER, "source extractor")
    spec = importlib.util.spec_from_file_location("worker_source", helpers)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    private = out / "source"
    source = worker.extract(args.c291, private)
    graph = git(args.c291, "show", f"{worker.PIN}:src/llama-graph.cpp")
    need(hashlib.sha256(graph).hexdigest() == GRAPH, "graph source")
    for path in ("ggml/src/ggml-cpu/ggml-cpu-impl.h", "ggml/src/ggml-impl.h"):
        header = git(args.c269, "show", f"{C269}:{path}")
        (private / Path(path).name).write_bytes(header)
    libdir = args.c269 / "build-c269-cuda" / "bin"
    for name, digest in LIBS.items():
        need(sha(libdir / name) == digest, "provider " + name)
    cpu, base = [libdir / name for name in LIBS]
    exe, tap = out / "fixture", out / "tap.so"
    cxx = "/usr/bin/g++"
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "LD_LIBRARY_PATH": str(libdir),
        "LD_BIND_NOW": "1",
        "CUDA_VISIBLE_DEVICES": "",
        "OMP_NUM_THREADS": "8",
        "TESY_CPU_WAVE_SKIP_PARKED": "1",
    }
    start_time = time.monotonic()

    def command(name, argv, timeout, child_env=None):
        log = out / (name + ".log")
        with log.open("xb") as f:
            subprocess.run(
                argv,
                stdout=f,
                stderr=subprocess.STDOUT,
                env=child_env or env,
                timeout=min(timeout, max(1, 175 - (time.monotonic() - start_time))),
                check=True,
            )
        return log.read_text()

    receipt.update(
        commit=head,
        c291=worker.PIN,
        c291_tree=worker.TREE,
        c269=C269,
        source=source,
        graph_source_sha256=GRAPH,
        protocol_sha256=PROTOCOL,
        libs=LIBS,
        own_sha256={
            name: sha(HERE / name) for name in ("fixture.cpp", "tap.cpp", "tap.h", "run.py")
        },
        compiler_sha256=sha(Path(cxx)),
        unit=args.unit,
        arms=[],
    )
    includes = ["-I" + str(private / d) for d in ("include", "src", "ggml/include", ".")]
    common = [cxx, "-std=c++17", "-O2", "-g0", "-pthread", "-fPIC", *includes]
    command(
        "build-tap",
        [*common, "-shared", HERE / "tap.cpp", base, "-ldl", "-Wl,-z,defs", "-o", tap],
        90,
    )
    command(
        "build-fixture",
        [
            *common,
            "-pie",
            "-ffunction-sections",
            "-fdata-sections",
            "-DTESY_C47_CPU_SKIP_PARKED",
            HERE / "fixture.cpp",
            *[private / "src" / name for name in worker.BUILD_INPUTS],
            "-Wl,--gc-sections",
            cpu,
            base,
            "-ldl",
            "-o",
            exe,
        ],
        120,
    )
    receipt["executable_sha256"] = sha(exe)
    receipt["tap_sha256"] = sha(tap)
    for mode in MODES[:2]:
        child = env if mode == "BASE" else {**env, "LD_PRELOAD": str(tap)}
        listing = command(
            "loader-" + mode, ["/lib64/ld-linux-x86-64.so.2", "--list", exe], 10, child
        )
        need("not found" not in listing, "loader unresolved")
        names = [line.split() for line in listing.splitlines() if line.strip()]
        need(
            not any(
                any(
                    tag in Path(row[0]).name
                    for tag in ("libcuda", "libnvidia", "libggml-cuda", "libllama")
                )
                for row in names
            ),
            "accelerator or model provider",
        )
        for path in (cpu, base):
            need(
                any(
                    len(r) > 2 and r[0] == path.name.rsplit(".", 2)[0] and Path(r[2]).samefile(path)
                    for r in names
                ),
                "loader provider",
            )
        need((str(tap) in listing) == (mode == "OFF"), "loader observer selection")
    for n in (5, 20, 32):
        baseline = None
        for mode in MODES:
            label = f"{n}-{mode}"
            output = out / (label + ".bin")
            child = env if mode == "BASE" else {**env, "LD_PRELOAD": str(tap)}
            log = command(label, [exe, mode, str(n), output, cpu], 30, child)
            metadata = {}
            for line in log.splitlines():
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key in ("graph", "mode"):
                    metadata[key] = value
                elif key in (
                    "rows",
                    "hits",
                    "entries",
                    "forwarded",
                    "remaps",
                    "start",
                    "ready",
                    "consumer",
                    "resolution",
                    "min_tick",
                    "threads",
                    "different",
                    "splits",
                ):
                    metadata[key] = int(value)
            raw = output.read_bytes()
            limits = verdict(mode, n, raw, metadata, baseline)
            if baseline is None:
                baseline = (raw, metadata["graph"])
            receipt["arms"].append({**metadata, "sha256": sha(output), "span": limits})
    need(time.monotonic() - start_time < 180, "time budget")
    total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    need(total + 65536 < OUTPUT, "output cap")
    peak = int((cg / "memory.peak").read_text())
    need(
        peak <= MEMORY
        and (cg / "memory.events").read_text() == events0
        and int((cg / "memory.swap.current").read_text()) == 0,
        "resource events",
    )
    receipt.update(
        memory_peak_bytes=peak,
        memory_events=events0,
        artifact_bytes_before_receipt=total,
        status="PASS_CPU_READY_MARKER",
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("c269", "c291", "new-output-dir"):
        p.add_argument("--" + name, required=True, type=Path)
    for name in ("unit", "commit"):
        p.add_argument("--" + name, required=True)
    args = p.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    receipt = {"status": "FAIL_PRESERVED"}
    try:
        run(args, receipt)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        receipt["error"] = str(exc)
    (args.new_output_dir / "receipt.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n"
    )
    return int(receipt["status"] != "PASS_CPU_READY_MARKER")


if __name__ == "__main__":
    sys.exit(main())
