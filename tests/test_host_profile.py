from __future__ import annotations

from tesy.host_profile import validate_reference_host


def _profile() -> dict:
    return {
        "schema": "tesy.reference_host.v1",
        "id": "fixture",
        "require_physical_host": True,
        "platform_system": "Linux",
        "cpu_model_contains": "HX 370",
        "logical_cpus": 24,
        "gpu_count": 1,
        "gpu_name_contains": "RTX 4060 Laptop",
        "ram_total_bytes_min": 30,
        "ram_total_bytes_max": 40,
        "vram_total_bytes_min": 7,
        "vram_total_bytes_max": 9,
    }


def _snapshot() -> dict:
    return {
        "platform": {"system": "Linux"},
        "virtualization": {"status": "PHYSICAL", "kind": "none"},
        "cpu": {"model": "AMD Ryzen AI 9 HX 370", "logical_cpus": 24},
        "memory": {"total_bytes": 32},
        "gpu": {
            "gpus": [
                {
                    "name": "NVIDIA GeForce RTX 4060 Laptop GPU",
                    "memory_total_bytes": 8,
                }
            ]
        },
    }


def test_reference_host_pass():
    result = validate_reference_host(_snapshot(), _profile())
    assert result["status"] == "PASS"


def test_reference_host_rejects_virtualized_host():
    snapshot = _snapshot()
    snapshot["virtualization"] = {"status": "VIRTUALIZED", "kind": "kvm"}
    result = validate_reference_host(snapshot, _profile())
    assert result["status"] == "FAIL"


def test_reference_host_is_inconclusive_when_physical_state_unknown():
    snapshot = _snapshot()
    snapshot["virtualization"] = {"status": "UNKNOWN", "kind": None}
    result = validate_reference_host(snapshot, _profile())
    assert result["status"] == "INCONCLUSIVE"


def test_reference_host_fails_wrong_gpu():
    snapshot = _snapshot()
    snapshot["gpu"]["gpus"][0]["name"] = "Different GPU"
    result = validate_reference_host(snapshot, _profile())
    assert result["status"] == "FAIL"


def test_reference_host_is_inconclusive_without_gpu_inventory():
    snapshot = _snapshot()
    snapshot["gpu"] = {"status": "NOT_AVAILABLE"}
    result = validate_reference_host(snapshot, _profile())
    assert result["status"] == "INCONCLUSIVE"
