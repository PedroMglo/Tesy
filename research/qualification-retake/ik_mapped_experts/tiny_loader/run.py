"""Build one small R03 client, or audit its real CPU GPT-OSS loader in three processes."""

import argparse
import hashlib
import json
import math
import os
import resource
import struct
import subprocess
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
FRONT = run_path(str(HERE.parent / "frontend/run.py"))
need, sha = FRONT["need"], FRONT["sha"]
BASE = {
    "src/libllama.so": "aa1e18b41a8f04ed396e885f24288965a8961e611261e173774e9f9cd538b74a",
    "ggml/src/libggml.so": "5395348a4bffef748be95e7657cbd25dd2ceaaa50f4f00e0f9d58dc742329c0c",
}
MODES = ("OFF", "DEFER", "DEFER_PREFETCH")


def expected_drops(layout):
    ranges = sorted(
        (start, start + n) for name, (start, n, _) in layout.items() if "_exps." in name
    )
    merged = []
    for a, b in ranges:
        if merged and a == merged[-1][1]:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    full = [(-(-a // 4096) * 4096, b // 4096 * 4096) for a, b in merged]
    return [(a, b - a, 4, 0) for a, b in full if b > a]


def grade(mode, text, layout, model_bytes, raw):
    def values(prefix):
        return [
            tuple(map(int, s.split()[1:])) for s in text.splitlines() if s.startswith(prefix + " ")
        ]

    maps = values("MAP")
    need(len(maps) == 1 and maps[0][:3] == (0, model_bytes, 1) and maps[0][3] & 1, "original mmap")
    need(bool(maps[0][3] & 0x8000) == (mode == "OFF"), "bulk MAP_POPULATE")
    hints = [v for v in values("POSIX") if v[2] == 3]
    need(hints == ([(0, model_bytes, 3, 0)] if mode == "OFF" else []), "bulk WILLNEED")
    drops = sorted(v for v in values("MAD") if v[2] == 4)
    need(drops == ([] if mode == "OFF" else expected_drops(layout)), "DONTNEED expert ranges")
    seen = {}
    for row in text.splitlines():
        if row.startswith("VIEW "):
            _, name, offset, size, kind = row.split()
            need(name not in seen, "duplicate expert tensor")
            seen[name] = list(map(int, (offset, size, kind)))
    views = {k: v for k, v in layout.items() if "_exps." in k}
    need(len(views) == 12 and seen == views, "view range, size or solver type")
    pool = values("POOL")
    need(len(pool) == 1 and pool[0][2] == int(mode == "DEFER_PREFETCH"), "worker pool")
    rss = values("RSS")
    need(len(rss) == 1 and 0 < rss[0][0] < 150 * 1024, "resident budget")
    need(len(raw) == 128, "logits size")
    logits = struct.unpack("<32f", raw)
    need(all(map(math.isfinite, logits)) and min(logits) < max(logits), "finite nonconstant logits")
    return {
        "mapped_expert_weights": 6,
        "mapped_expert_biases": 6,
        "mmap_flags": maps[0][3],
        "whole_file_willneed": len(hints),
        "dropped_ranges": drops,
        "dropped_bytes": sum(v[1] for v in drops),
        "tasks_before_after": pool[0][:2],
        "pool_enabled": bool(pool[0][2]),
        "max_rss_kib": rss[0][0],
        "logits_sha256": hashlib.sha256(raw).hexdigest(),
        "greedy": logits.index(max(logits)),
    }


def bounded():
    resource.setrlimit(resource.RLIMIT_AS, (150 << 20, 150 << 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))


def sources():
    return {f: sha(HERE / f) for f in ("protocol.md", "data.py", "probe.cpp", "run.py")}


def run(a, out, result):
    src, obj = a.source.resolve(), a.objects.resolve()
    commit = subprocess.check_output(["git", "-C", src, "rev-parse", "HEAD"], text=True).strip()
    need(
        commit == FRONT["PIN"]
        and not subprocess.check_output(["git", "-C", src, "status", "--porcelain"]),
        "dirty or unexpected upstream",
    )
    for name, value in BASE.items():
        FRONT["pinned"](obj / name, value)
    result.update(sources=sources(), ik_commit=commit, libraries=BASE)
    if a.mode == "build":
        binary = out / "probe"
        cmd = [
            "/usr/bin/c++",
            "-std=c++17",
            "-O1",
            "-pthread",
            "-rdynamic",
            str(HERE / "probe.cpp"),
            *("-I" + str(src / p) for p in ("include", "ggml/include", "ggml/src")),
            str(obj / "src/libllama.so"),
            str(obj / "ggml/src/libggml.so"),
            "-ldl",
            "-o",
            str(binary),
        ]
        with (out / "compile.log").open("xb") as log:
            subprocess.run(cmd, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=60)
        result.update(binary_sha256=sha(binary), closure=FRONT["closure"](binary, obj), cmd=cmd)
        return "PASS_TINY_IK_CLIENT_BUILD"
    b = json.loads(FRONT["pinned"](a.build / "receipt.json", a.build_sha256).read_bytes())
    binary = FRONT["pinned"](a.build / "probe", b["binary_sha256"])
    need(
        b["status"] == "PASS_TINY_IK_CLIENT_BUILD"
        and b["ik_commit"] == commit
        and b["sources"]["probe.cpp"] == result["sources"]["probe.cpp"]
        and FRONT["closure"](binary, obj) == b["closure"],
        "linked client",
    )
    model = out / "synthetic.gguf"
    layout = run_path(str(HERE / "data.py"))["generate"](model)
    need(model.stat().st_size <= 32 << 20, "synthetic file cap")
    result.update(
        gguf_bytes=model.stat().st_size,
        gguf_sha256=sha(model),
        tensors=len(layout),
        build_sha256=a.build_sha256,
        arms={},
        model="synthetic",
        original_model_loads=0,
    )
    ref = None
    env = FRONT["env"](obj) | {
        "MALLOC_ARENA_MAX": "1",
        "OMP_NUM_THREADS": "1",
        "OMP_STACKSIZE": "512K",
    }
    for mode in MODES:
        root = out / mode
        root.mkdir()
        with (root / "stdout").open("xb") as sout, (root / "stderr").open("xb") as serr:
            proc = subprocess.run(
                [binary, model, mode, root / "logits.f32"],
                env=env,
                stdout=sout,
                stderr=serr,
                preexec_fn=bounded,
                timeout=30,
            )
        result["arms"][mode] = {
            "returncode": proc.returncode,
            "stdout_sha256": sha(root / "stdout"),
            "stderr_sha256": sha(root / "stderr"),
        }
        need(proc.returncode == 0, "client " + mode + " rc=" + str(proc.returncode))
        raw = (root / "logits.f32").read_bytes()
        arm = grade(mode, (root / "stdout").read_text(), layout, model.stat().st_size, raw)
        result["arms"][mode].update(arm)
        if ref is None:
            ref = raw
        need(raw == ref, "full logits " + mode)
    a0, a1, a2 = [result["arms"][m]["tasks_before_after"] for m in MODES]
    deltas = [v - u for u, v in (a0, a1, a2)]
    need(deltas[0] == deltas[1] == deltas[2] - 4, "four incremental workers")
    need(sha(model) == result["gguf_sha256"], "changed fixture")
    return "PASS_TINY_IK_DEFERRED_GPT_OSS_LOGITS"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("build", "run"))
    p.add_argument("--source", required=True, type=Path)
    p.add_argument("--objects", required=True, type=Path)
    p.add_argument("--new-output-dir", required=True, type=Path)
    p.add_argument("--build", type=Path)
    p.add_argument("--build-sha256")
    a = p.parse_args()
    out = a.new_output_dir.resolve()
    out.mkdir(mode=0o700, exist_ok=False)
    result = {}
    try:
        result["status"] = run(a, out, result)
    except Exception as e:
        result.update(status="FAIL_PRESERVED", error=str(e))
    with (out / ".receipt.tmp").open("x") as h:
        json.dump(result, h, indent=2, sort_keys=True)
        h.write("\n")
    os.rename(out / ".receipt.tmp", out / "receipt.json")
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
