from __future__ import annotations

from dataclasses import dataclass
from typing import Any

GIB = 1024**3


@dataclass(frozen=True)
class CapacityPolicy:
    reserve_ram_bytes: int = 6 * GIB
    reserve_vram_bytes: int = 1024**3
    staging_ram_bytes: int = 1024**3


def transport_floor_seconds(byte_count: int, bytes_per_second: float) -> float:
    if isinstance(byte_count, bool) or byte_count < 0:
        raise ValueError("byte_count must be a non-negative integer")
    if bytes_per_second <= 0 or bytes_per_second != bytes_per_second:
        raise ValueError("bytes_per_second must be finite and positive")
    return byte_count / bytes_per_second


def plan_capacity(
    model: dict[str, Any],
    snapshot: dict[str, Any],
    artifact_bytes: int | None,
    policy: CapacityPolicy | None = None,
) -> dict[str, Any]:
    p = policy or CapacityPolicy()
    memory = snapshot.get("memory", {})
    ram_total = memory.get("total_bytes")
    ram_available = memory.get("available_bytes")
    gpu = snapshot.get("gpu", {})
    gpus = gpu.get("gpus", []) if isinstance(gpu, dict) else []
    vram_total = gpus[0].get("memory_total_bytes") if gpus else None
    vram_free = gpus[0].get("memory_free_bytes") if gpus else None

    reasons: list[str] = []
    status = "ADMISSIBLE_FOR_TEST"

    if not isinstance(ram_total, int) or not isinstance(ram_available, int):
        status = "INCONCLUSIVE"
        reasons.append("live RAM inventory unavailable")
    if not isinstance(vram_total, int) or not isinstance(vram_free, int):
        status = "INCONCLUSIVE"
        reasons.append("live NVIDIA VRAM inventory unavailable")
    if artifact_bytes is None:
        status = "INCONCLUSIVE"
        reasons.append("exact local model artifact size unavailable")

    usable_ram_total = (
        max(0, ram_total - p.reserve_ram_bytes - p.staging_ram_bytes)
        if isinstance(ram_total, int)
        else None
    )
    usable_ram_now = (
        max(0, ram_available - p.staging_ram_bytes)
        if isinstance(ram_available, int)
        else None
    )
    usable_vram_total = (
        max(0, vram_total - p.reserve_vram_bytes)
        if isinstance(vram_total, int)
        else None
    )
    usable_vram_now = (
        max(0, vram_free - p.reserve_vram_bytes)
        if isinstance(vram_free, int)
        else None
    )

    backing = "UNKNOWN"
    if artifact_bytes is not None and usable_ram_total is not None:
        if artifact_bytes <= usable_ram_total:
            backing = "RAM_CAPACITY_PLAUSIBLE"
        else:
            backing = "NVME_BACKING_REQUIRED"
            reasons.append(
                "model artifact exceeds conservative RAM capacity; true out-of-core path required"
            )

    if artifact_bytes is not None and artifact_bytes <= 0:
        status = "NOGO"
        reasons.append("model artifact is empty")

    return {
        "schema": "tesy.capacity_plan.v1",
        "classification": "ESTIMATED_FROM_LIVE_CAPACITY",
        "status": status,
        "model_id": model.get("id"),
        "artifact_bytes": artifact_bytes,
        "usable_ram_total_bytes": usable_ram_total,
        "usable_ram_now_bytes": usable_ram_now,
        "usable_vram_total_bytes": usable_vram_total,
        "usable_vram_now_bytes": usable_vram_now,
        "backing_class": backing,
        "policy": {
            "reserve_ram_bytes": p.reserve_ram_bytes,
            "reserve_vram_bytes": p.reserve_vram_bytes,
            "staging_ram_bytes": p.staging_ram_bytes,
        },
        "reasons": reasons,
        "claim_boundary": (
            "Capacity admission only. This is not a performance, exactness, "
            "load-success or chat-usability result."
        ),
    }
