import copy
import math

import pytest

from tesy.mixed_residency_benchmark import (
    MixedResidencyBenchmarkError,
    validate_mixed_residency_raw,
    weighted_trace_diagnostic,
)


def _stats(base: float) -> dict:
    samples = [base + i * 0.01 for i in range(21)]
    ordered = sorted(samples)
    return {
        "median_ms": ordered[len(ordered) // 2],
        "p95_ms": ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)],
        "min_ms": samples[0],
        "max_ms": samples[-1],
        "mean_ms": sum(samples) / len(samples),
        "samples_ms": samples,
    }


def _raw() -> dict:
    cases = []
    for h in range(5):
        cases.append(
            {
                "gpu_hits": h,
                "cpu_misses": 4 - h,
                "source_expert_ids": [0, 1, 2, 3],
                "global_mix_weight": 0.25,
                "direct_wall": _stats(1.0 - 0.15 * h),
                "parity": {
                    "max_abs": 0.001,
                    "max_abs_ref": 2.0,
                    "relative_max": 0.0005,
                    "cosine": 0.99999,
                    "status": "PASS",
                },
            }
        )
    return {
        "schema": "tesy.mixed_residency_stage_b_raw.v1",
        "classification": "MEASURED_MIXED_RESIDENCY_FFN_DIAGNOSTIC",
        "layer": 0,
        "threads": 12,
        "warmup": 3,
        "samples": 21,
        "inner": 5,
        "n_embd": 2880,
        "top_k": 4,
        "expert_count_model": 32,
        "encoded_bytes_per_expert": 13_253_760,
        "weight_type": "mxfp4",
        "bias_type": "f32",
        "weight_shape": [2880, 2880, 32],
        "bias_shape": [2880, 32],
        "cpu_weight_buffer_type": "CPU_REPACK",
        "cpu_bias_buffer_type": "CPU",
        "expert_ids": [0, 1, 2, 3],
        "mix_weights": [0.25, 0.25, 0.25, 0.25],
        "measurement_order": [0, 4, 1, 3, 2],
        "cases": cases,
        "claim_boundary": "isolated diagnostic",
    }


def _histogram() -> dict:
    return {
        "schema": "tesy.mixed_residency_hit_histogram.v1",
        "classification": "TRACE_DERIVED_RESIDENCY_OPPORTUNITY",
        "routing_groups": 360,
        "gpu_resident_experts_per_top4_histogram": {
            "0": 39,
            "1": 26,
            "2": 62,
            "3": 128,
            "4": 105,
        },
    }


def test_validate_mixed_residency_raw_accepts_full_h_curve():
    summary = validate_mixed_residency_raw(_raw())
    assert summary["status"] == "PASS"
    assert [row["gpu_hits"] for row in summary["cases"]] == [0, 1, 2, 3, 4]
    assert summary["cases"][0]["speedup_vs_all_cpu"] == pytest.approx(1.0)
    assert summary["cases"][4]["speedup_vs_all_cpu"] > 1.0


def test_validate_mixed_residency_raw_rejects_missing_case():
    payload = _raw()
    payload["cases"].pop(1)
    with pytest.raises(MixedResidencyBenchmarkError, match="h=0..4"):
        validate_mixed_residency_raw(payload)


def test_validate_mixed_residency_raw_rejects_failed_parity():
    payload = _raw()
    payload["cases"][3]["parity"]["status"] = "FAIL"
    with pytest.raises(MixedResidencyBenchmarkError, match="parity did not PASS"):
        validate_mixed_residency_raw(payload)


def test_validate_mixed_residency_raw_rejects_order_change():
    payload = _raw()
    payload["measurement_order"] = [0, 1, 2, 3, 4]
    with pytest.raises(MixedResidencyBenchmarkError, match="measurement_order mismatch"):
        validate_mixed_residency_raw(payload)


def test_weighted_trace_diagnostic_uses_group_counts():
    summary = validate_mixed_residency_raw(_raw())
    result = weighted_trace_diagnostic(summary, _histogram())

    expected = sum(
        count * summary["cases"][h]["median_ms"]
        for h, count in enumerate([39, 26, 62, 128, 105])
    ) / 360

    assert result["status"] == "PASS"
    assert result["weighted_median_case_ms"] == pytest.approx(expected)
    assert result["speedup_equivalent_vs_all_cpu"] > 1.0


def test_weighted_trace_diagnostic_rejects_histogram_count_mismatch():
    histogram = copy.deepcopy(_histogram())
    histogram["gpu_resident_experts_per_top4_histogram"]["4"] -= 1

    with pytest.raises(MixedResidencyBenchmarkError, match="count sum mismatch"):
        weighted_trace_diagnostic(
            validate_mixed_residency_raw(_raw()),
            histogram,
        )


def test_validate_mixed_residency_raw_rejects_tampered_statistics():
    payload = copy.deepcopy(_raw())
    payload["cases"][2]["direct_wall"]["median_ms"] += 0.005
    with pytest.raises(
        MixedResidencyBenchmarkError,
        match="median_ms does not match raw samples",
    ):
        validate_mixed_residency_raw(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("warmup", 2, "warmup must equal frozen value 3"),
        ("samples", 20, "samples must equal frozen value 21"),
        ("inner", 4, "inner must equal frozen value 5"),
    ],
)
def test_validate_mixed_residency_raw_rejects_workload_change(field, value, message):
    payload = copy.deepcopy(_raw())
    payload[field] = value
    if field == "samples":
        for row in payload["cases"]:
            row["direct_wall"]["samples_ms"] = row["direct_wall"]["samples_ms"][:value]
    with pytest.raises(MixedResidencyBenchmarkError, match=message):
        validate_mixed_residency_raw(payload)
