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
    p.add_argument("--backend", choices=["stock", "streaming"], required=True)
    p.add_argument("--variant", required=True)
    p.add_argument("--workload", required=True)
    p.add_argument("--cache-condition", required=True)
    p.add_argument("--timeout-s", type=int, default=300)
    p.add_argument("--max-rss-gib", type=float, default=24.0)
    p.add_argument("--min-available-gib", type=float, default=6.0)
    p.add_argument("--max-gpu-mib", type=float, default=7600.0)
    p.add_argument("command", nargs=argparse.REMAINDER)
    a = p.parse_args()
    cmd = a.command[1:] if a.command and a.command[0] == "--" else a.command
    if not cmd or not Path(cmd[0]).is_file():
        p.error("command must start with an existing local binary path")
    if not a.run_id.replace("-", "").replace("_", "").isalnum():
        p.error("run-id must contain only letters, digits, dash or underscore")

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
        "backend": a.backend,
        "backend_sha": revision,
        "binary_sha256": sha256(cmd[0]),
        "variant": a.variant,
        "workload": a.workload,
        "cache_condition": a.cache_condition,
        "command": cmd,
        "limits": {"timeout_s": a.timeout_s, "max_rss_gib": a.max_rss_gib,
                   "min_available_gib": a.min_available_gib, "max_gpu_mib": a.max_gpu_mib},
        "cgroup_limit_enforced": False,
        "publication": "local only; stdout/stderr are untracked",
        "samples_path": str(stem) + ".samples.jsonl",
    }
    with open(str(stem) + ".stdout", "wb") as stdout, open(str(stem) + ".stderr", "wb") as stderr, open(str(stem) + ".samples.jsonl", "w") as samples:
        process = subprocess.Popen(cmd, stdout=stdout, stderr=stderr, start_new_session=True)
        reason = None
        maxima = {"rss_bytes": 0, "swap_bytes": 0, "gpu_used_mib": 0, "gpu_temperature_c": 0}
        last = {}
        try:
            while process.poll() is None:
                status = proc_status(process.pid)
                avail = mem_available()
                gpu = gpu_state()
                sample = {"elapsed_s": round(time.monotonic() - t0, 3), "proc": status,
                          "mem_available_bytes": avail, "gpu": gpu}
                samples.write(json.dumps(sample) + "\n")
                samples.flush()
                last = sample
                maxima["rss_bytes"] = max(maxima["rss_bytes"], status.get("VmRSS", 0))
                maxima["swap_bytes"] = max(maxima["swap_bytes"], status.get("VmSwap", 0))
                if gpu:
                    maxima["gpu_used_mib"] = max(maxima["gpu_used_mib"], gpu["used_mib"])
                    maxima["gpu_temperature_c"] = max(maxima["gpu_temperature_c"], gpu["temperature_c"])
                if sample["elapsed_s"] > a.timeout_s:
                    reason = "TIMEOUT"
                elif status.get("VmSwap", 0) > 0:
                    reason = "SWAP_USED"
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
        rc = process.returncode
    manifest.update({"ended_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                     "elapsed_s": round(time.monotonic() - t0, 3), "returncode": rc,
                     "stop_reason": reason, "maxima": maxima, "last_sample": last,
                     "stdout_path": str(stem) + ".stdout", "stderr_path": str(stem) + ".stderr"})
    Path(str(stem) + ".json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: manifest[k] for k in ("run_id", "elapsed_s", "returncode", "stop_reason", "maxima")}))
    return 0 if rc == 0 and reason is None else 1


if __name__ == "__main__":
    sys.exit(main())
