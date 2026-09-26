#!/usr/bin/env python3
"""Run a local llama.cpp command with a resource watchdog and compact manifest."""

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def proc_status(pid):
    try:
        lines = Path(f"/proc/{pid}/status").read_text().splitlines()
        d = {}
        for line in lines:
            if line.startswith(("VmRSS:", "VmSwap:", "VmHWM:")):
                k, v = line.split(":", 1)
                d[k] = int(v.strip().split()[0]) * 1024
        for line in Path(f"/proc/{pid}/io").read_text().splitlines():
            if line.startswith(("read_bytes:", "rchar:", "syscr:")):
                k, v = line.split(":", 1)
                d[k] = int(v)
        return d
    except (FileNotFoundError, ProcessLookupError):
        return {}


def mem_available():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    return None


def cgroup_state():
    try:
        rel = next(line.split("::", 1)[1].strip() for line in Path("/proc/self/cgroup").read_text().splitlines() if "::" in line)
        base = Path("/sys/fs/cgroup") / rel.lstrip("/")
        def number(name):
            value = (base / name).read_text().strip()
            return None if value == "max" else int(value)
        events = {}
        for line in (base / "memory.events").read_text().splitlines():
            k, v = line.split()
            events[k] = int(v)
        memstat = {}
        for line in (base / "memory.stat").read_text().splitlines():
            k, v = line.split()
            if k in ("anon", "file", "kernel", "file_mapped", "shmem"):
                memstat[k] = int(v)
        return {"path": rel, "memory_max": number("memory.max"),
                "swap_max": number("memory.swap.max"), "memory_current": number("memory.current"),
                "swap_current": number("memory.swap.current"), "memory_stat": memstat,
                "events": events}
    except (OSError, ValueError, StopIteration):
        return None


def model_fd_state(pid, model_path):
    if not model_path:
        return None
    result = {"open": 0, "direct": 0, "buffered": 0}
    try:
        for fd in Path(f"/proc/{pid}/fd").iterdir():
            try:
                if os.readlink(fd) != model_path:
                    continue
                flags_line = next(line for line in Path(f"/proc/{pid}/fdinfo/{fd.name}").read_text().splitlines() if line.startswith("flags:"))
                flags = int(flags_line.split()[1], 8)
                result["open"] += 1
                result["direct" if flags & os.O_DIRECT else "buffered"] += 1
            except (OSError, StopIteration, ValueError):
                continue
    except OSError:
        pass
    return result


def gpu_state():
    try:
        p = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,temperature.gpu,power.draw", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3, check=True,
        )
        parts = p.stdout.strip().splitlines()[0].split(",")
        return {"used_mib": float(parts[0]), "temperature_c": float(parts[1]), "power_w": float(parts[2])}
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def stop_own_group(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--model-id", required=True)
    p.add_argument("--backend", choices=["stock", "streaming", "streaming-reference"], required=True)
    p.add_argument("--variant", required=True)
    p.add_argument("--workload", required=True)
    p.add_argument("--cache-condition", required=True)
    p.add_argument("--timeout-s", type=int, default=300)
    p.add_argument("--max-rss-gib", type=float, default=24.0)
    p.add_argument("--min-available-gib", type=float, default=6.0)
    p.add_argument("--max-gpu-mib", type=float, default=7600.0)
    p.add_argument("--env", action="append", default=[], help="explicit KEY=VALUE for the child")
    p.add_argument("--stdin-file", help="input file for a bounded multi-turn CLI run")
    p.add_argument("command", nargs=argparse.REMAINDER)
    a = p.parse_args()
    cmd = a.command[1:] if a.command and a.command[0] == "--" else a.command
    if not cmd or not Path(cmd[0]).is_file():
        p.error("command must start with an existing local binary path")
    model_path = next((str(Path(arg).resolve()) for arg in cmd if arg.endswith(".gguf") and Path(arg).is_file()), None)
    if a.stdin_file and not Path(a.stdin_file).is_file():
        p.error("stdin-file must exist")
    if not a.run_id.replace("-", "").replace("_", "").isalnum():
        p.error("run-id must contain only letters, digits, dash or underscore")
    child_env = os.environ.copy()
    explicit_env = {}
    for assignment in a.env:
        if "=" not in assignment:
            p.error("--env requires KEY=VALUE")
        key, value = assignment.split("=", 1)
        if not key or not key.replace("_", "").isalnum():
            p.error("invalid environment variable name")
        explicit_env[key] = value
        child_env[key] = value

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    stem = out / a.run_id
    for suffix in (".json", ".stdout", ".stderr", ".samples.jsonl"):
        if Path(str(stem) + suffix).exists():
            p.error(f"run-id already exists: {a.run_id}")

    backend_dir = ROOT / "backends" / a.backend
    revision = subprocess.check_output(["git", "-C", str(backend_dir), "rev-parse", "HEAD"], text=True).strip()
    t0 = time.monotonic()
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest = {
        "run_id": a.run_id,
        "started_utc": started,
        "model_id": a.model_id,
        "model_path": model_path,
        "backend": a.backend,
        "backend_sha": revision,
        "binary_sha256": sha256(cmd[0]),
        "variant": a.variant,
        "workload": a.workload,
        "cache_condition": a.cache_condition,
        "command": cmd,
        "explicit_env": explicit_env,
        "stdin_file": a.stdin_file,
        "stdin_sha256": sha256(a.stdin_file) if a.stdin_file else None,
        "limits": {"timeout_s": a.timeout_s, "max_rss_gib": a.max_rss_gib,
                   "min_available_gib": a.min_available_gib, "max_gpu_mib": a.max_gpu_mib},
        "cgroup_start": cgroup_state(),
        "publication": "local only; stdout/stderr are untracked",
        "samples_path": str(stem) + ".samples.jsonl",
    }
    manifest["cgroup_limit_enforced"] = bool(manifest["cgroup_start"] and
                                                manifest["cgroup_start"]["memory_max"] is not None and
                                                manifest["cgroup_start"]["swap_max"] == 0)
    with open(str(stem) + ".stdout", "wb") as stdout, open(str(stem) + ".stderr", "wb") as stderr, open(str(stem) + ".samples.jsonl", "w") as samples:
        stdin = open(a.stdin_file, "rb") if a.stdin_file else subprocess.DEVNULL
        process = subprocess.Popen(cmd, stdin=stdin, stdout=stdout, stderr=stderr,
                                   start_new_session=True, env=child_env)
        reason = None
        maxima = {"rss_bytes": 0, "swap_bytes": 0, "cgroup_memory_bytes": 0,
                  "cgroup_file_bytes": 0, "gpu_used_mib": 0, "gpu_temperature_c": 0,
                  "direct_model_fds": 0, "buffered_model_fds": 0}
        last = {}
        try:
            while process.poll() is None:
                status = proc_status(process.pid)
                avail = mem_available()
                gpu = gpu_state()
                cg = cgroup_state()
                fds = model_fd_state(process.pid, model_path)
                sample = {"elapsed_s": round(time.monotonic() - t0, 3), "proc": status,
                          "mem_available_bytes": avail, "gpu": gpu, "cgroup": cg,
                          "model_fds": fds}
                samples.write(json.dumps(sample) + "\n")
                samples.flush()
                last = sample
                maxima["rss_bytes"] = max(maxima["rss_bytes"], status.get("VmRSS", 0))
                maxima["swap_bytes"] = max(maxima["swap_bytes"], status.get("VmSwap", 0))
                if cg:
                    maxima["cgroup_memory_bytes"] = max(maxima["cgroup_memory_bytes"], cg["memory_current"] or 0)
                    maxima["cgroup_file_bytes"] = max(maxima["cgroup_file_bytes"], cg["memory_stat"].get("file", 0))
                if gpu:
                    maxima["gpu_used_mib"] = max(maxima["gpu_used_mib"], gpu["used_mib"])
                    maxima["gpu_temperature_c"] = max(maxima["gpu_temperature_c"], gpu["temperature_c"])
                if fds:
                    maxima["direct_model_fds"] = max(maxima["direct_model_fds"], fds["direct"])
                    maxima["buffered_model_fds"] = max(maxima["buffered_model_fds"], fds["buffered"])
                if sample["elapsed_s"] > a.timeout_s:
                    reason = "TIMEOUT"
                elif status.get("VmSwap", 0) > 0:
                    reason = "SWAP_USED"
                elif cg and cg["swap_current"] and cg["swap_current"] > 0:
                    reason = "CGROUP_SWAP_USED"
                elif cg and manifest["cgroup_start"] and cg["events"].get("oom", 0) > manifest["cgroup_start"]["events"].get("oom", 0):
                    reason = "CGROUP_OOM"
                elif cg and manifest["cgroup_start"] and cg["events"].get("max", 0) > manifest["cgroup_start"]["events"].get("max", 0):
                    reason = "CGROUP_LIMIT_HIT"
                elif status.get("VmRSS", 0) > a.max_rss_gib * 2**30:
                    reason = "RSS_GUARD"
                elif avail is not None and avail < a.min_available_gib * 2**30:
                    reason = "HOST_HEADROOM_GUARD"
                elif gpu and gpu["used_mib"] > a.max_gpu_mib:
                    reason = "GPU_GUARD"
                if reason:
                    stop_own_group(process)
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            reason = "INTERRUPTED"
            stop_own_group(process)
        finally:
            stop_own_group(process)
            if a.stdin_file:
                stdin.close()
        rc = process.returncode
    manifest.update({"ended_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                     "elapsed_s": round(time.monotonic() - t0, 3), "returncode": rc,
                     "stop_reason": reason, "maxima": maxima, "last_sample": last,
                     "stdout_path": str(stem) + ".stdout", "stderr_path": str(stem) + ".stderr",
                     "cgroup_end": cgroup_state()})
    Path(str(stem) + ".json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: manifest[k] for k in ("run_id", "elapsed_s", "returncode", "stop_reason", "maxima")}))
    return 0 if rc == 0 and reason is None else 1


if __name__ == "__main__":
    sys.exit(main())
