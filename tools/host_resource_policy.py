#!/usr/bin/env python3
"""Prospective host/device resource policy for physical Tesy campaigns.

Historical campaigns keep their frozen guards. New campaigns should derive
device limits from vendor/device telemetry and keep experimental admission
margins explicitly separate from hardware limits.
"""

from __future__ import annotations

import math
import re
from typing import Any

GIB = 2**30
MIB = 2**20

CPU_TJMAX_C = 100.0
CPU_WARNING_C = 95.0
DEFAULT_GPU_MEMORY_RESERVE_MIB = 512
DEFAULT_HOST_RESERVE_GIB = 2.0
TEMP_SANITY_MAX_C = 150.0

_NVIDIA_TEMP_PATTERNS = {
    "max_operating_c": re.compile(r"GPU Max Operating Temp\s*:\s*([0-9.]+)\s*C", re.I),
    "slowdown_c": re.compile(r"GPU Slowdown Temp\s*:\s*([0-9.]+)\s*C", re.I),
    "shutdown_c": re.compile(r"GPU Shutdown Temp\s*:\s*([0-9.]+)\s*C", re.I),
    "target_c": re.compile(r"GPU Target Temperature\s*:\s*([0-9.]+)\s*C", re.I),
}


class ResourcePolicyError(ValueError):
    pass


def _finite_number(value: Any, where: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ResourcePolicyError(f"{where}: finite number required")
    return float(value)


def _plausible_temp(value: Any) -> float | None:
    try:
        number = _finite_number(value, "temperature")
    except ResourcePolicyError:
        return None
    return number if -20.0 < number < TEMP_SANITY_MAX_C else None


def parse_nvidia_temperature_query(text: str) -> dict[str, float | None]:
    result: dict[str, float | None] = {key: None for key in _NVIDIA_TEMP_PATTERNS}
    if type(text) is not str:
        return result
    for key, pattern in _NVIDIA_TEMP_PATTERNS.items():
        match = pattern.search(text)
        if match:
            result[key] = _plausible_temp(float(match.group(1)))
    return result


def parse_gpu_csv(csv_line: str) -> dict[str, Any]:
    if type(csv_line) is not str:
        raise ResourcePolicyError("gpu_csv: string required")
    parts = [part.strip() for part in csv_line.split(",")]
    if len(parts) < 5:
        raise ResourcePolicyError("gpu_csv: expected name,total,used,temp,driver")
    name, total, used, temp, driver = parts[:5]
    total_mib = _finite_number(float(total), "gpu memory.total")
    used_mib = _finite_number(float(used), "gpu memory.used")
    current_c = _plausible_temp(float(temp))
    if total_mib <= 0 or used_mib < 0 or used_mib > total_mib or current_c is None:
        raise ResourcePolicyError("gpu_csv: invalid capacity/temperature")
    return {
        "name": name,
        "memory_total_mib": total_mib,
        "memory_used_mib": used_mib,
        "temperature_c": current_c,
        "driver_version": driver,
    }


def _find_cpu_tctl(sensors: dict[str, Any]) -> float:
    values = []
    for name, device in sensors.items():
        if not str(name).startswith("k10temp-") or type(device) is not dict:
            continue
        tctl = device.get("Tctl")
        if type(tctl) is dict:
            value = _plausible_temp(tctl.get("temp1_input"))
            if value is not None:
                values.append(value)
    if len(values) != 1:
        raise ResourcePolicyError(f"expected exactly one CPU Tctl sensor, got {len(values)}")
    return values[0]


def _find_nvme_composite(sensors: dict[str, Any]) -> dict[str, Any]:
    if type(sensors) is not dict:
        raise ResourcePolicyError("sensors: object required")
    candidates = []
    for name, device in sensors.items():
        if not str(name).startswith("nvme-") or type(device) is not dict:
            continue
        composite = device.get("Composite")
        if type(composite) is not dict:
            continue
        current = _plausible_temp(composite.get("temp1_input"))
        warning = _plausible_temp(composite.get("temp1_max"))
        critical = _plausible_temp(composite.get("temp1_crit"))
        if current is None:
            continue
        if warning is not None and critical is not None and critical < warning:
            warning = None
            critical = None
        candidates.append({
            "sensor": name,
            "current_c": current,
            "warning_c": warning,
            "critical_c": critical,
        })
    if len(candidates) != 1:
        raise ResourcePolicyError(
            f"expected exactly one usable NVMe Composite sensor, got {len(candidates)}"
        )
    return candidates[0]


def derive_policy(
    *,
    memory: dict[str, int],
    gpu_csv: str,
    sensors: dict[str, Any],
    nvidia_temperature_query: str = "",
    gpu_memory_reserve_mib: int = DEFAULT_GPU_MEMORY_RESERVE_MIB,
    host_reserve_gib: float = DEFAULT_HOST_RESERVE_GIB,
) -> dict[str, Any]:
    required = ("MemTotal", "MemAvailable")
    if type(memory) is not dict or any(type(memory.get(k)) is not int for k in required):
        raise ResourcePolicyError("memory: MemTotal/MemAvailable integer bytes required")
    total = memory["MemTotal"]
    available = memory["MemAvailable"]
    if total <= 0 or available < 0 or available > total:
        raise ResourcePolicyError("memory: invalid totals")

    reserve_bytes = int(host_reserve_gib * GIB)
    if reserve_bytes <= 0 or reserve_bytes >= total:
        raise ResourcePolicyError("host reserve invalid")
    allocatable_now = max(0, min(total - reserve_bytes, available - reserve_bytes))
    quantum = 256 * MIB
    suggested_cgroup_max = (allocatable_now // quantum) * quantum

    gpu = parse_gpu_csv(gpu_csv)
    if type(gpu_memory_reserve_mib) is not int or gpu_memory_reserve_mib < 256:
        raise ResourcePolicyError("GPU reserve must be an integer >=256 MiB")
    gpu_admission_max = gpu["memory_total_mib"] - gpu_memory_reserve_mib
    if gpu_admission_max <= 0:
        raise ResourcePolicyError("GPU reserve consumes device capacity")

    gpu_thresholds = parse_nvidia_temperature_query(nvidia_temperature_query)
    gpu_warning = gpu_thresholds["max_operating_c"] or gpu_thresholds["target_c"]
    # Slowdown is performance telemetry, not a safety failure. Keep one degree
    # below the device-reported shutdown threshold as the prospective stop.
    gpu_stop = (gpu_thresholds["shutdown_c"] - 1.0
                if gpu_thresholds["shutdown_c"] is not None else None)
    if gpu_stop is not None and gpu_warning is not None and gpu_stop < gpu_warning:
        raise ResourcePolicyError("GPU threshold ordering invalid")

    cpu_current = _find_cpu_tctl(sensors)
    nvme = _find_nvme_composite(sensors)

    return {
        "schema": "tesy-resource-policy-v1",
        "classification": {
            "device_limit": "manufacturer/firmware/device threshold",
            "warning": "valid operating region requiring telemetry, not automatic failure",
            "experiment_admission": "prospective margin for safe/comparable execution, not a device limit",
        },
        "cpu": {
            "current_c": cpu_current,
            "warning_c": CPU_WARNING_C,
            "device_limit_c": CPU_TJMAX_C,
            "source": "AMD Ryzen AI 9 HX 370 Tjmax",
        },
        "gpu": {
            **gpu,
            "warning_c": gpu_warning,
            "stop_c": gpu_stop,
            "shutdown_c": gpu_thresholds["shutdown_c"],
            "slowdown_c": gpu_thresholds["slowdown_c"],
            "max_operating_c": gpu_thresholds["max_operating_c"],
            "target_c": gpu_thresholds["target_c"],
            "memory_reserve_mib": gpu_memory_reserve_mib,
            "memory_admission_max_mib": gpu_admission_max,
            "memory_admission_class": "EXPERIMENT_ADMISSION",
        },
        "memory": {
            "total_bytes": total,
            "available_bytes": available,
            "host_reserve_bytes": reserve_bytes,
            "host_reserve_class": "EXPERIMENT_ADMISSION",
            "suggested_cgroup_max_bytes": suggested_cgroup_max,
            "suggested_cgroup_class": "EXPERIMENT_ADMISSION",
            "swap_policy": "ZERO_FOR_EXPLICIT_STREAMING_CAMPAIGNS",
        },
        "nvme": {
            **nvme,
            "warning_class": "DEVICE_THRESHOLD" if nvme["warning_c"] is not None else "UNKNOWN",
            "critical_class": "DEVICE_THRESHOLD" if nvme["critical_c"] is not None else "UNKNOWN",
        },
        "prospective_limits": {
            "cpu_warning_c": CPU_WARNING_C,
            "cpu_max_c": CPU_TJMAX_C,
            "gpu_warning_c": gpu_warning,
            "gpu_max_c": gpu_stop,
            "nvme_warning_c": nvme["warning_c"],
            "nvme_max_c": nvme["critical_c"],
            "gpu_max_mib": gpu_admission_max,
            "min_mem_available_bytes": reserve_bytes,
            "suggested_cgroup_max_bytes": suggested_cgroup_max,
        },
    }


def freeze_protocol_resource_limits(policy: dict[str, Any], *, cgroup_memory_max_bytes: int) -> dict[str, Any]:
    """Freeze resource limits for a new campaign from a preflight policy.

    The cgroup hard cap is a profile choice. It must fit the live suggested cap.
    A 512 MiB in-cgroup margin avoids using the OOM boundary as a benchmark target.
    RSS is recorded against the cgroup cap rather than given a separate artificial
    one-GiB reservation.
    """
    if type(cgroup_memory_max_bytes) is not int or cgroup_memory_max_bytes <= 512 * MIB:
        raise ResourcePolicyError("cgroup cap too small")
    suggested = policy["memory"]["suggested_cgroup_max_bytes"]
    if cgroup_memory_max_bytes > suggested:
        raise ResourcePolicyError("cgroup cap exceeds live prospective admission")
    gpu_stop = policy["gpu"]["stop_c"]
    nvme_stop = policy["nvme"]["critical_c"]
    if gpu_stop is None or nvme_stop is None:
        raise ResourcePolicyError("device thermal stop threshold unavailable")
    return {
        "cgroup_memory_max_bytes": cgroup_memory_max_bytes,
        "memory_max_bytes": cgroup_memory_max_bytes - 512 * MIB,
        "rss_max_bytes": policy["memory"]["total_bytes"],
        "gpu_max_mib": policy["gpu"]["memory_admission_max_mib"],
        "min_mem_available_bytes": policy["memory"]["host_reserve_bytes"],
        "cpu_max_c": policy["cpu"]["device_limit_c"],
        "gpu_max_c": gpu_stop,
        "nvme_max_c": nvme_stop,
    }


def ready_for_launch(policy: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons = []
    gpu = policy["gpu"]
    mem = policy["memory"]
    nvme = policy["nvme"]
    cpu = policy["cpu"]

    if gpu["memory_used_mib"] >= gpu["memory_admission_max_mib"]:
        reasons.append("gpu-memory-admission")
    if mem["available_bytes"] < mem["host_reserve_bytes"]:
        reasons.append("host-memory-reserve")
    if mem["suggested_cgroup_max_bytes"] <= 0:
        reasons.append("no-cgroup-headroom")
    if gpu["temperature_c"] >= (gpu["stop_c"] if gpu["stop_c"] is not None else math.inf):
        reasons.append("gpu-device-threshold")
    if nvme["critical_c"] is not None and nvme["current_c"] >= nvme["critical_c"]:
        reasons.append("nvme-critical-threshold")
    if cpu["device_limit_c"] != CPU_TJMAX_C:
        reasons.append("cpu-policy-invalid")
    if cpu["current_c"] >= cpu["device_limit_c"]:
        reasons.append("cpu-device-limit")
    return not reasons, reasons
