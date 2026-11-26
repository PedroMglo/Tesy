"""Bounded, offline build of a pinned upstream CUDA server. Requires a capped scope."""

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

PIN = "e95426f16982054c379ca7bdc8186996dd22f0fe"
TREE = "3c5105435231a5095af520b352396d526d483dab"
GIB = 1 << 30
TOOLS = {
    "cc": "/usr/bin/gcc-15",
    "cxx": "/usr/bin/g++-15",
    "nvcc": "/usr/local/cuda/bin/nvcc",
    "ptxas": "/usr/local/cuda/bin/ptxas",
    "cuobjdump": "/usr/local/cuda/bin/cuobjdump",
    "cmake": "/usr/bin/cmake",
    "ninja": "/usr/bin/ninja",
}
FLAGS = [
    "-DCMAKE_BUILD_TYPE=Release",
    "-DCMAKE_CUDA_ARCHITECTURES=89-real",
    "-DCMAKE_CUDA_HOST_COMPILER=" + TOOLS["cxx"],
    "-DCMAKE_CUDA_COMPILER=" + TOOLS["nvcc"],
    "-DCMAKE_CXX_COMPILER=" + TOOLS["cxx"],
    "-DCMAKE_C_COMPILER=" + TOOLS["cc"],
    "-DBUILD_SHARED_LIBS=ON",
    "-DGGML_CUDA=ON",
    "-DGGML_CUDA_NCCL=OFF",
    "-DGGML_CUDA_FA=ON",
    "-DGGML_CUDA_FA_QUANTS=f16-f16",
    "-DGGML_CCACHE=OFF",
    "-DLLAMA_BUILD_TESTS=OFF",
    "-DLLAMA_BUILD_EXAMPLES=OFF",
    "-DLLAMA_BUILD_APP=OFF",
    "-DLLAMA_BUILD_UI=OFF",
    "-DLLAMA_USE_PREBUILT_UI=OFF",
    "-DLLAMA_OPENSSL=OFF",
    "-DFETCHCONTENT_FULLY_DISCONNECTED=ON",
]
ABI = [
    "--load-mode",
    "--lazy-mode",
    "--no-repack",
    "--no-host",
    "--fit",
    "--gpu-layers",
    "--cpu-moe",
    "--moe-cache-mib",
    "--moe-cache-cpu-share",
    "--ctx-size",
    "--parallel",
    "--batch-size",
    "--ubatch-size",
    "--cache-type-k",
    "--cache-type-v",
    "--no-warmup",
]


def digest(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def capture(args):
    return subprocess.check_output(args, text=True, timeout=30).strip()


def check(value, message):
    if not value:
        raise RuntimeError(message)


def record(out, info):
    tmp = out / ".receipt.pending"
    tmp.write_text(json.dumps(info, indent=2, sort_keys=True) + "\n")
    tmp.replace(out / "receipt.json")


def run(repo, private, public):
    public.mkdir(exist_ok=False)
    private.mkdir(exist_ok=False)
    started = time.monotonic()
    info = {
        "decision": "FAIL",
        "started_utc": datetime.now(UTC).isoformat(),
        "pin": PIN,
        "tree": TREE,
        "cmake_flags": FLAGS,
        "jobs": 5,
        "protocol_sha256": digest(Path(__file__).with_name("protocol.md")),
        "hardware_scope": "COMPILER_AND_MODEL_FREE_CLI",
        "source_clean_after": None,
        "telemetry": {},
        "steps": {},
    }
    src = private / "source"
    build = private / "build"
    tmp = private / "tmp"
    tmp.mkdir()
    env = {
        **os.environ,
        "TMPDIR": str(tmp),
        "CUDA_VISIBLE_DEVICES": "",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ALLOW_PROTOCOL": "file",
        "LC_ALL": "C",
        "PATH": "/usr/local/cuda/bin:" + os.environ["PATH"],
    }
    cg = None
    tctl = None

    def tree_status():
        return capture(["git", "-C", src, "status", "--porcelain", "--untracked-files=all"])

    def sample():
        vals = info["telemetry"]
        temp = int(tctl.read_text()) / 1000
        mem = int((cg / "memory.current").read_text())
        fs = int(capture(["du", "-s", "-B1", private]).split()[0])
        vals["peak_sampled_new_disk_bytes"] = max(vals.get("peak_sampled_new_disk_bytes", 0), fs)
        vals["peak_sampled_tctl_c"] = max(vals.get("peak_sampled_tctl_c", 0), temp)
        vals["peak_sampled_scope_bytes"] = max(vals.get("peak_sampled_scope_bytes", 0), mem)
        check(time.monotonic() - started < 1200, "elapsed_budget")
        check(fs <= 4 * GIB, "disk_budget")
        check(temp < 95, "temperature_budget")
        check(Path("/sys/class/power_supply/AC0/online").read_text().strip() == "1", "ac_power")

    def step(name, args):
        start = time.monotonic()
        info["stage"] = name
        with (private / (name + ".log")).open("wb") as log:
            proc = subprocess.Popen(
                args, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True
            )
            try:
                while proc.poll() is None:
                    sample()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        continue
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
        info["steps"][name] = {
            "returncode": proc.returncode,
            "s": round(time.monotonic() - start, 3),
        }
        check(proc.returncode == 0, "command_failed_" + name)
        return private / (name + ".log")

    try:
        cg_rel = Path("/proc/self/cgroup").read_text().strip().split("::")[-1]
        cg = Path("/sys/fs/cgroup") / cg_rel.lstrip("/")
        check((cg / "memory.max").read_text().strip() == str(6 * GIB), "cgroup_max")
        check((cg / "memory.swap.max").read_text().strip() == "0", "cgroup_swap_max")
        tctl = next(
            p.with_name("temp1_input")
            for p in Path("/sys/class/hwmon").glob("*/name")
            if p.read_text().strip() == "k10temp"
        )
        check(int(tctl.read_text()) < 85000, "initial_temperature")
        free = int(re.search(r"MemAvailable:\s+(\d+)", Path("/proc/meminfo").read_text())[1]) * 1024
        check(free >= 8 * GIB and shutil.disk_usage(private).free >= 4 * GIB, "initial_resources")
        info["available_initial_bytes"] = free
        sample()
        info["toolchain"] = {
            key: {"sha256": digest(path), "version": capture([path, "--version"]).splitlines()}
            for key, path in TOOLS.items()
        }
        # The upstream object store is shallow and its HEAD belongs to the historical
        # build. An ordinary local clone advertises only refs and can omit this pin.
        step("init", ["git", "init", "--quiet", src])
        git_dir = Path(capture(["git", "-C", repo, "rev-parse", "--absolute-git-dir"]))
        (src / ".git/objects/info/alternates").write_text(str(git_dir / "objects") + "\n")
        if (git_dir / "shallow").is_file():
            shutil.copyfile(git_dir / "shallow", src / ".git/shallow")
        step("checkout", ["git", "-C", src, "checkout", "--detach", PIN])
        check(capture(["git", "-C", src, "rev-parse", "HEAD"]) == PIN, "commit")
        check(capture(["git", "-C", src, "rev-parse", "HEAD^{tree}"]) == TREE, "tree")
        check(not tree_status(), "initial_source_dirty")
        step("configure", ["cmake", "-S", src, "-B", build, "-G", "Ninja", *FLAGS])
        step("compile", ["cmake", "--build", build, "--target", "llama-server", "-j", "5"])
        server = build / "bin/llama-server"
        ver = step("version", [server, "--version"]).read_text()
        check(PIN[:7] in ver, "version_pin")
        help_text = step("help", [server, "--help"]).read_text()
        for flag in ABI:
            check(flag in help_text, "missing_cli_" + flag)
        info["abi"] = ABI
        info["version_lines"] = [
            x for x in ver.splitlines() if "version:" in x or "built with" in x
        ]
        info["server_sha256"] = digest(server)
        cuda = (build / "bin/libggml-cuda.so").resolve()
        listing = step("gpu_elf", [TOOLS["cuobjdump"], "-lelf", cuda]).read_text()
        check("sm_89" in listing, "sm89_elf")
        info["sm89_elf_entries"] = len([line for line in listing.splitlines() if "sm_89" in line])
        ld = step("libraries", ["ldd", server, cuda]).read_text()
        check("not found" not in ld, "unresolved_lib")
        own = {}
        for name, path in re.findall(r"^\s*(\S+) => (\S+) \(", ld, re.MULTILINE):
            if name.startswith(("libllama", "libggml", "libmtmd")):
                loc = Path(path).resolve()
                check(loc.is_relative_to(build), "external_backend")
                own[name] = digest(loc)
        check(
            any("libllama.so" in x for x in own) and any("libggml-cuda" in x for x in own),
            "backend_set",
        )
        info["own_libs_sha256"] = own
        info["source_clean_after"] = not tree_status()
        check(info["source_clean_after"], "dirty_after")
        sample()
        info["decision"] = "PASS_STOCK_BUILD_AND_MODEL_FREE_CLI"
    except Exception as exc:
        info["reason"] = str(exc).replace(str(private), "<private>")
        raise
    finally:
        info["elapsed_s"] = round(time.monotonic() - started, 3)
        if cg and (cg / "memory.events").is_file():
            info["memory_events"] = dict(
                x.split() for x in (cg / "memory.events").read_text().splitlines()
            )
            info["scope_peak_bytes"] = int((cg / "memory.peak").read_text())
        record(public, info)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--llama-git", required=True, type=Path)
    ap.add_argument("--private-root", required=True, type=Path)
    ap.add_argument("--new-output", required=True, type=Path)
    a = ap.parse_args()
    try:
        run(a.llama_git.resolve(), a.private_root.resolve(), a.new_output.resolve())
    except Exception as err:
        print(str(err), file=sys.stderr)
        sys.exit(1)
