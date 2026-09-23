from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _meminfo() -> dict[str, int]:
    text = _read_text(Path("/proc/meminfo"))
    if text is None:
        return {}
    result: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        fields = raw.strip().split()
        if not fields:
            continue
        try:
            value = int(fields[0])
        except ValueError:
            continue
        multiplier = 1024 if len(fields) > 1 and fields[1].lower() == "kb" else 1
        result[key] = value * multiplier
    return result


def _cpu_model() -> str | None:
    text = _read_text(Path("/proc/cpuinfo"))
    if text is None:
        return None
    for line in text.splitlines():
        if line.lower().startswith("model name") and ":" in line:
            return line.split(":", 1)[1].strip()
    return None


def _run(command: list[str], timeout_s: float = 3.0) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env={**os.environ, "LC_ALL": "C"},
        )
    except FileNotFoundError:
        return {"status": "NOT_AVAILABLE", "command": command}
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "command": command}
    return {
        "status": "OK" if completed.returncode == 0 else "ERROR",
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "command": command,
    }


def _nvidia() -> dict[str, Any]:
    query = (
        "name,memory.total,memory.free,driver_version,"
        "temperature.gpu,pstate,pci.bus_id"
    )
    result = _run(
        [
            "nvidia-smi",
            f"--query-gpu={query}",
            "--format=csv,noheader,nounits",
        ],
        timeout_s=5.0,
    )
    if result["status"] != "OK":
        return result
    rows: list[dict[str, Any]] = []
    for line in result["stdout"].splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 7:
            continue
        name, total_mib, free_mib, driver, temp_c, pstate, pci_bus_id = parts
        try:
            total_bytes = int(float(total_mib) * 1024 * 1024)
            free_bytes = int(float(free_mib) * 1024 * 1024)
            temp = float(temp_c)
        except ValueError:
            continue
        rows.append(
            {
                "name": name,
                "memory_total_bytes": total_bytes,
                "memory_free_bytes": free_bytes,
                "driver_version": driver,
                "temperature_c": temp,
                "pstate": pstate,
                "pci_bus_id": pci_bus_id,
            }
        )
    return {"status": "OK", "gpus": rows, "command": result["command"]}


def collect_snapshot(path_for_disk: Path | None = None) -> dict[str, Any]:
    mem = _meminfo()
    disk_path = (path_for_disk or Path.cwd()).resolve()
    try:
        usage = shutil.disk_usage(disk_path)
        disk: dict[str, Any] = {
            "path": str(disk_path),
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
        }
    except OSError as exc:
        disk = {"path": str(disk_path), "status": "ERROR", "error": str(exc)}

    nvcc = _run(["nvcc", "--version"])
    snapshot = {
        "schema": "tesy.hardware_snapshot.v1",
        "classification": "MEASURED_HOST_STATE",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "cpu": {
            "model": _cpu_model(),
            "logical_cpus": os.cpu_count(),
        },
        "memory": {
            "total_bytes": mem.get("MemTotal"),
            "available_bytes": mem.get("MemAvailable"),
            "swap_total_bytes": mem.get("SwapTotal"),
            "swap_free_bytes": mem.get("SwapFree"),
        },
        "gpu": _nvidia(),
        "cuda_toolkit": nvcc,
        "disk": disk,
    }
    return snapshot


def dumps(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True)
