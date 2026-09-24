import pytest

from tesy.placement_telemetry import (
    PlacementTelemetryError,
    parse_server_model_buffers,
    validate_placement_telemetry,
)


def test_parse_server_model_buffers_separates_cuda_and_mmap_host_span():
    payload = parse_server_model_buffers(
        "load_tensors: offloaded 25/25 layers to GPU\n"
        "load_tensors:      CUDA0 model buffer size = 6095.35 MiB\n"
        "load_tensors: CPU_Mapped model buffer size = 10949.33 MiB\n"
    )
    assert payload["gpu_model_mib"] == pytest.approx(6095.35)
    assert payload["host_runtime_buffer_mib"] == pytest.approx(10949.33)
    assert payload["mapped_host_buffer_mib"] == pytest.approx(10949.33)
    assert payload["mapped_host_buffer_names"] == ["CPU_Mapped"]
    assert payload["offloaded_layers"] == {"loaded": 25, "total": 25}


def test_validate_placement_telemetry_accepts_cuda_parity_with_noncomparable_mmap_span():
    payload = validate_placement_telemetry(
        fit_print_text="CUDA0 6095 114 449\nHost 5440 0 16\n",
        server_stderr_text=(
            "load_tensors: offloaded 25/25 layers to GPU\n"
            "load_tensors: CUDA0 model buffer size = 6095.35 MiB\n"
            "load_tensors: CPU_Mapped model buffer size = 10949.33 MiB\n"
        ),
        placement_id="auto-fit-frozen",
        tolerance_mib=2.0,
    )
    assert payload["schema"] == "tesy.stock_placement_telemetry.v2"
    assert payload["status"] == "PASS"
    assert payload["cuda0_delta_mib"] == pytest.approx(0.35)
    assert payload["projected_logical_model_mib"] == {
        "CUDA0": 6095.0,
        "Host": 5440.0,
    }
    assert payload["observed_runtime_model_buffers"]["Host_mmap_span_mib"] == pytest.approx(
        10949.33
    )
    assert payload["host_comparability"]["status"] == "NOT_COMPARABLE_MMAP_SPAN"
    assert payload["host_comparability"]["equality_gate"] is False
    assert payload["mismatches"] == []


def test_validate_placement_telemetry_rejects_cuda_mismatch():
    payload = validate_placement_telemetry(
        fit_print_text="CUDA0 6095 114 449\nHost 5440 0 16\n",
        server_stderr_text=(
            "load_tensors: offloaded 25/25 layers to GPU\n"
            "load_tensors: CUDA0 model buffer size = 6000.00 MiB\n"
            "load_tensors: CPU_Mapped model buffer size = 10949.33 MiB\n"
        ),
        placement_id="n-cpu-moe-12",
        tolerance_mib=2.0,
    )
    assert payload["status"] == "FAIL"
    assert len(payload["mismatches"]) == 1
    assert "CUDA0 model buffer differs" in payload["mismatches"][0]


def test_validate_placement_telemetry_requires_mmap_host_buffer_when_host_projected():
    payload = validate_placement_telemetry(
        fit_print_text="CUDA0 6095 114 449\nHost 5440 0 16\n",
        server_stderr_text=(
            "load_tensors: offloaded 25/25 layers to GPU\n"
            "load_tensors: CUDA0 model buffer size = 6095.25 MiB\n"
            "load_tensors: CPU model buffer size = 5440.00 MiB\n"
        ),
        placement_id="n-cpu-moe-12",
        tolerance_mib=2.0,
    )
    assert payload["status"] == "FAIL"
    assert any("no mmap-backed Host model buffer" in item for item in payload["mismatches"])


@pytest.mark.parametrize("host_row", [
    "Other_Mapped model buffer size = 5440.00 MiB",
    "CPU_Mapped model buffer size = 0.00 MiB",
])
def test_validate_placement_telemetry_requires_positive_cpu_mapped_buffer(host_row):
    payload = validate_placement_telemetry(
        fit_print_text="CUDA0 6095 114 449\nHost 5440 0 16\n",
        server_stderr_text=(
            "load_tensors: offloaded 25/25 layers to GPU\n"
            "load_tensors: CUDA0 model buffer size = 6095.25 MiB\n"
            f"load_tensors: {host_row}\n"
        ),
        placement_id="n-cpu-moe-12",
    )
    assert payload["status"] == "FAIL"
    assert any("no mmap-backed Host model buffer" in item for item in payload["mismatches"])


def test_parse_server_model_buffers_rejects_nonfinite_size():
    with pytest.raises(PlacementTelemetryError, match="invalid model buffer size"):
        parse_server_model_buffers(
            "load_tensors: offloaded 25/25 layers to GPU\n"
            f"load_tensors: CUDA0 model buffer size = {'9' * 400} MiB\n"
        )


def test_validate_placement_telemetry_rejects_nonfinite_tolerance():
    with pytest.raises(PlacementTelemetryError, match="finite and non-negative"):
        validate_placement_telemetry(
            fit_print_text="CUDA0 6095 114 449\nHost 5440 0 16\n",
            server_stderr_text="",
            placement_id="auto-fit-frozen",
            tolerance_mib=float("nan"),
        )


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
