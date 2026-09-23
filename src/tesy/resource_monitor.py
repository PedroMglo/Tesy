from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


def _proc_status(pid: int) -> dict[str, int]:
    result: dict[str, int] = {}
    path = Path(f"/proc/{pid}/status")
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        parts = raw.strip().split()
        if key in {"VmRSS", "VmSwap"} and parts:
            result[key + "_bytes"] = int(parts[0]) * 1024
    return result


def _meminfo() -> dict[str, int]:
    result: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        parts = raw.strip().split()
        if key in {"MemAvailable", "SwapFree"} and parts:
            result[key + "_bytes"] = int(parts[0]) * 1024
    return result


def _gpu() -> dict:
    command = [
        "nvidia-smi",
        "--query-gpu=memory.used,temperature.gpu,pstate,power.draw",
        "--format=csv,noheader,nounits",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return {"status": "ERROR", "stderr": completed.stderr.strip()}
    parts = [item.strip() for item in completed.stdout.strip().split(",")]
    if len(parts) != 4:
        return {"status": "ERROR", "stderr": "unexpected nvidia-smi row"}
    try:
        return {
            "status": "OK",
            "memory_used_bytes": int(float(parts[0]) * 1024 * 1024),
            "temperature_c": float(parts[1]),
            "pstate": parts[2],
            "power_w": float(parts[3]),
        }
    except ValueError:
        return {"status": "ERROR", "stderr": completed.stdout.strip()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--interval-ms", type=int, default=200)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to replace {args.output}")
    if args.interval_ms < 50:
        raise SystemExit("interval-ms must be >= 50")

    with args.output.open("x", encoding="utf-8") as handle:
        while Path(f"/proc/{args.pid}").exists():
            row = {
                "monotonic_ns": time.monotonic_ns(),
                "process": _proc_status(args.pid),
                "system": _meminfo(),
                "gpu": _gpu(),
            }
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
            time.sleep(args.interval_ms / 1000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
