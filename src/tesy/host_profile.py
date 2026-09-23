from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class HostProfileError(ValueError):
    pass


def load_host_profile(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HostProfileError(f"cannot read host profile {path}: {exc}") from exc
    if payload.get("schema") != "tesy.reference_host.v1":
        raise HostProfileError("unsupported host profile schema")
    return payload


def validate_reference_host(
    snapshot: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    unknown: list[str] = []

    platform_system = snapshot.get("platform", {}).get("system")
    expected_system = profile.get("platform_system")
    if not isinstance(platform_system, str):
        unknown.append("platform.system unavailable")
    elif platform_system != expected_system:
        failures.append(
            f"platform.system expected {expected_system!r}, got {platform_system!r}"
        )

    cpu = snapshot.get("cpu", {})
    cpu_model = cpu.get("model") if isinstance(cpu, dict) else None
    cpu_contains = profile.get("cpu_model_contains")
    if not isinstance(cpu_model, str):
        unknown.append("CPU model unavailable")
    elif not isinstance(cpu_contains, str) or cpu_contains not in cpu_model:
        failures.append(
            f"CPU model must contain {cpu_contains!r}, got {cpu_model!r}"
        )

    logical_cpus = cpu.get("logical_cpus") if isinstance(cpu, dict) else None
    expected_cpus = profile.get("logical_cpus")
    if not isinstance(logical_cpus, int) or isinstance(logical_cpus, bool):
        unknown.append("logical CPU count unavailable")
    elif logical_cpus != expected_cpus:
        failures.append(
            f"logical CPUs expected {expected_cpus}, got {logical_cpus}"
        )

    memory = snapshot.get("memory", {})
    ram_total = memory.get("total_bytes") if isinstance(memory, dict) else None
    if not isinstance(ram_total, int) or isinstance(ram_total, bool):
        unknown.append("RAM total unavailable")
    else:
        ram_min = profile.get("ram_total_bytes_min")
        ram_max = profile.get("ram_total_bytes_max")
        if not isinstance(ram_min, int) or not isinstance(ram_max, int):
            raise HostProfileError("RAM profile bounds must be integers")
        if not ram_min <= ram_total <= ram_max:
            failures.append(
                f"RAM total {ram_total} outside [{ram_min}, {ram_max}]"
            )

    gpu = snapshot.get("gpu", {})
    gpus = gpu.get("gpus") if isinstance(gpu, dict) else None
    if not isinstance(gpus, list):
        unknown.append("NVIDIA GPU inventory unavailable")
    else:
        expected_count = profile.get("gpu_count")
        if len(gpus) != expected_count:
            failures.append(
                f"GPU count expected {expected_count}, got {len(gpus)}"
            )
        if gpus:
            first = gpus[0]
            name = first.get("name") if isinstance(first, dict) else None
            name_contains = profile.get("gpu_name_contains")
            if not isinstance(name, str):
                unknown.append("GPU name unavailable")
            elif not isinstance(name_contains, str) or name_contains not in name:
                failures.append(
                    f"GPU name must contain {name_contains!r}, got {name!r}"
                )

            vram = first.get("memory_total_bytes") if isinstance(first, dict) else None
            if not isinstance(vram, int) or isinstance(vram, bool):
                unknown.append("GPU VRAM total unavailable")
            else:
                vram_min = profile.get("vram_total_bytes_min")
                vram_max = profile.get("vram_total_bytes_max")
                if not isinstance(vram_min, int) or not isinstance(vram_max, int):
                    raise HostProfileError("VRAM profile bounds must be integers")
                if not vram_min <= vram <= vram_max:
                    failures.append(
                        f"VRAM total {vram} outside [{vram_min}, {vram_max}]"
                    )

    if failures:
        status = "FAIL"
    elif unknown:
        status = "INCONCLUSIVE"
    else:
        status = "PASS"

    return {
        "schema": "tesy.reference_host_check.v1",
        "classification": "MEASURED_HOST_IDENTITY_CHECK",
        "profile_id": profile.get("id"),
        "status": status,
        "failures": failures,
        "unknown": unknown,
        "claim_boundary": (
            "Host identity only. PASS does not qualify current free RAM/VRAM, "
            "driver/CUDA, storage mounts, thermal state, process isolation or "
            "model/runtime performance."
        ),
    }
