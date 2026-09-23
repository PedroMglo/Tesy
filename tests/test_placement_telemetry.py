import pytest

from tesy.placement_telemetry import (
    PlacementTelemetryError,
    parse_server_model_buffers,
    validate_placement_telemetry,
)


def test_parse_server_model_buffers_sums_host_buffers():
    payload = parse_server_model_buffers(
        "load_tensors: offloaded 25/25 layers to GPU\n"
        "load_tensors:      CUDA0 model buffer size = 6095.25 MiB\n"
        "load_tensors:  CPU_Mapped model buffer size = 5439.50 MiB\n"
        "load_tensors:         CPU model buffer size = 0.50 MiB\n"
    )
    assert payload["gpu_model_mib"] == pytest.approx(6095.25)
    assert payload["host_model_mib"] == pytest.approx(5440.0)
    assert payload["offloaded_layers"] == {"loaded": 25, "total": 25}


def test_validate_placement_telemetry_accepts_small_rounding_delta():
    payload = validate_placement_telemetry(
        fit_print_text="CUDA0 6095 114 449\nHost 5440 0 16\n",
        server_stderr_text=(
            "load_tensors: offloaded 25/25 layers to GPU\n"
            "load_tensors: CUDA0 model buffer size = 6095.60 MiB\n"
            "load_tensors: CPU_Mapped model buffer size = 5439.40 MiB\n"
        ),
        placement_id="n-cpu-moe-12",
        tolerance_mib=2.0,
    )
    assert payload["status"] == "PASS"
    assert payload["placement_id"] == "n-cpu-moe-12"
    assert payload["mismatches"] == []


def test_validate_placement_telemetry_rejects_gpu_mismatch():
    payload = validate_placement_telemetry(
        fit_print_text="CUDA0 6095 114 449\nHost 5440 0 16\n",
        server_stderr_text=(
            "load_tensors: offloaded 25/25 layers to GPU\n"
            "load_tensors: CUDA0 model buffer size = 6000.00 MiB\n"
            "load_tensors: CPU_Mapped model buffer size = 5440.00 MiB\n"
        ),
        placement_id="n-cpu-moe-12",
        tolerance_mib=2.0,
    )
    assert payload["status"] == "FAIL"
    assert len(payload["mismatches"]) == 1
    assert "GPU model buffers differ" in payload["mismatches"][0]


def test_parse_server_model_buffers_rejects_multiple_gpus():
    with pytest.raises(PlacementTelemetryError, match="expected only CUDA0"):
        parse_server_model_buffers(
            "load_tensors: offloaded 25/25 layers to GPU\n"
            "load_tensors: CUDA0 model buffer size = 3000.00 MiB\n"
            "load_tensors: CUDA1 model buffer size = 3000.00 MiB\n"
            "load_tensors: CPU_Mapped model buffer size = 5000.00 MiB\n"
        )


def test_parse_server_model_buffers_requires_offload_row():
    with pytest.raises(
        PlacementTelemetryError,
        match="expected exactly one offloaded-layers row",
    ):
        parse_server_model_buffers(
            "load_tensors: CUDA0 model buffer size = 6095.00 MiB\n"
            "load_tensors: CPU_Mapped model buffer size = 5440.00 MiB\n"
        )
