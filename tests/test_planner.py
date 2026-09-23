from __future__ import annotations

import math

import pytest

from tesy.planner import GIB, CapacityPolicy, plan_capacity, transport_floor_seconds


def _snapshot(ram: int = 32 * GIB, available: int = 24 * GIB, vram: int = 8 * GIB):
    return {
        "memory": {"total_bytes": ram, "available_bytes": available},
        "gpu": {
            "gpus": [
                {
                    "memory_total_bytes": vram,
                    "memory_free_bytes": 7 * GIB,
                }
            ]
        },
    }


def test_transport_floor():
    assert transport_floor_seconds(10_000, 5_000.0) == 2.0


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan")])
def test_transport_floor_rejects_bad_bandwidth(bad):
    with pytest.raises(ValueError):
        transport_floor_seconds(1, bad)


def test_capacity_plausible_in_ram():
    result = plan_capacity(
        {"id": "m"},
        _snapshot(),
        artifact_bytes=12 * GIB,
        policy=CapacityPolicy(
            reserve_ram_bytes=6 * GIB,
            reserve_vram_bytes=1 * GIB,
            staging_ram_bytes=1 * GIB,
        ),
    )
    assert result["status"] == "ADMISSIBLE_FOR_TEST"
    assert result["backing_class"] == "RAM_CAPACITY_PLAUSIBLE"


def test_capacity_marks_nvme_when_model_exceeds_conservative_ram():
    result = plan_capacity({"id": "m"}, _snapshot(), artifact_bytes=30 * GIB)
    assert result["status"] == "ADMISSIBLE_FOR_TEST"
    assert result["backing_class"] == "NVME_BACKING_REQUIRED"


def test_capacity_inconclusive_without_gpu():
    snap = _snapshot()
    snap["gpu"] = {"status": "NOT_AVAILABLE"}
    result = plan_capacity({"id": "m"}, snap, artifact_bytes=12 * GIB)
    assert result["status"] == "INCONCLUSIVE"


def test_math_module_is_not_needed_for_nan_comparison():
    assert math.isnan(float("nan"))
