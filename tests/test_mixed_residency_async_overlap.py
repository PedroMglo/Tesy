import copy

import pytest

from tesy.mixed_residency_async_overlap import (
    validate_async_raw,
    weight_async,
)
from tesy.mixed_residency_overlap_bound import MixedResidencyOverlapBoundError


def _stats(median: float) -> dict:
    samples = [
        median - 0.002,
        median - 0.001,
        median,
        median + 0.001,
        median + 0.002,
    ]
    return {
        "median_ms": median,
        "p95_ms": samples[-1],
        "min_ms": samples[0],
        "max_ms": samples[-1],
        "mean_ms": sum(samples) / len(samples),
        "samples_ms": samples,
    }


def _parity() -> dict:
    return {
        "max_abs": 1e-7,
        "max_abs_ref": 2.0,
        "relative_max": 5e-8,
        "cosine": 0.99999,
        "status": "PASS",
    }


def _case(h: int, async_median: float | None = None) -> dict:
    cpu = 4 - h
    d2h = _stats(0.02) if cpu else None
    cpu_compute = _stats(0.20 + 0.10 * cpu) if cpu else None
    gpu_compute = _stats(0.10 + 0.03 * h) if h else None
    h2d = _stats(0.02) if cpu else None
    agg = _stats(0.04) if 0 < h < 4 else None

    if 0 < h < 4:
        component_sum = (
            d2h["median_ms"]
            + cpu_compute["median_ms"]
            + gpu_compute["median_ms"]
            + h2d["median_ms"]
            + agg["median_ms"]
        )
        bound = (
            d2h["median_ms"]
            + max(cpu_compute["median_ms"], gpu_compute["median_ms"])
            + h2d["median_ms"]
            + agg["median_ms"]
        )
    elif h == 0:
        component_sum = (
            d2h["median_ms"]
            + cpu_compute["median_ms"]
            + h2d["median_ms"]
        )
        bound = None
    else:
        component_sum = gpu_compute["median_ms"]
        bound = None

    direct = _stats(1.0)
    if h in {0, 4}:
        bound = direct["median_ms"]

    return {
        "gpu_hits": h,
        "cpu_misses": cpu,
        "source_expert_ids": [0, 1, 2, 3],
        "global_mix_weight": 0.25,
        "direct_wall": direct,
        "async_wall": (
            _stats(async_median)
            if async_median is not None
            else None
        ),
        "async_parity": (
            _parity()
            if async_median is not None
            else None
        ),
        "components": {
            "activation_d2h": d2h,
            "cpu_compute": cpu_compute,
            "gpu_compute": gpu_compute,
            "cpu_partial_h2d": h2d,
            "gpu_aggregation": agg,
        },
        "component_sum_median_ms": component_sum,
        "post_d2h_overlap_bound_median_ms": bound,
        "overlap_bound_speedup_vs_direct": (
            direct["median_ms"] / bound
        ),
        "parity": _parity(),
    }


def _payload(async_median: float = 0.80) -> dict:
    return {
        "schema": "tesy.mixed_residency_async_raw.v1",
        "classification": "MEASURED_MIXED_RESIDENCY_ASYNC_DIAGNOSTIC",
        "async_schedule": "post_d2h_gpu_enqueue_cpu_sync_gpu_wait",
        "paired_sample_order": "even_serial_async_odd_async_serial",
        "layer": 0,
        "threads": 12,
        "warmup": 3,
        "samples": 5,
        "inner": 5,
        "n_embd": 2880,
        "top_k": 4,
        "expert_count_model": 32,
        "encoded_bytes_per_expert": 13_253_760,
        "weight_type": "mxfp4",
        "bias_type": "f32",
        "weight_shape": [2880, 2880, 32],
        "bias_shape": [2880, 32],
        "cpu_weight_buffer_type": "CPU",
        "cpu_bias_buffer_type": "CPU",
        "gpu_async_capable": True,
        "cpu_async_capable": False,
        "expert_ids": [0, 1, 2, 3],
        "mix_weights": [0.25, 0.25, 0.25, 0.25],
        "measurement_order": [0, 4, 1, 3, 2],
        "cases": [
            _case(0),
            _case(1, async_median),
            _case(2, async_median),
            _case(3, async_median),
            _case(4),
        ],
        "claim_boundary": "async isolated diagnostic",
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


def test_validate_async_accepts_mixed_cases_and_serial_anchors():
    summary = validate_async_raw(_payload())

    assert summary["status"] == "PASS"
    assert summary["gpu_async_capable"] is True
    assert summary["cases"][0]["async_median_ms"] is None
    assert summary["cases"][4]["async_median_ms"] is None
    assert summary["cases"][2]["async_median_ms"] == pytest.approx(0.80)


def test_validate_async_rejects_anchor_candidate():
    payload = _payload()
    payload["cases"][0]["async_wall"] = _stats(0.8)
    payload["cases"][0]["async_parity"] = _parity()

    with pytest.raises(
        MixedResidencyOverlapBoundError,
        match="serial anchor",
    ):
        validate_async_raw(payload)


def test_validate_async_rejects_failed_async_parity():
    payload = _payload()
    payload["cases"][2]["async_parity"]["status"] = "FAIL"

    with pytest.raises(
        MixedResidencyOverlapBoundError,
        match="did not PASS",
    ):
        validate_async_raw(payload)


def test_validate_async_rejects_schedule_tampering():
    payload = _payload()
    payload["async_schedule"] = "different_schedule"

    with pytest.raises(
        MixedResidencyOverlapBoundError,
        match="scheduling identity",
    ):
        validate_async_raw(payload)


def test_validate_async_requires_gpu_async_capability():
    payload = _payload()
    payload["gpu_async_capable"] = False

    with pytest.raises(
        MixedResidencyOverlapBoundError,
        match="GPU backend",
    ):
        validate_async_raw(payload)


def test_weight_async_applies_frozen_ten_percent_gate():
    weighted = weight_async(
        validate_async_raw(_payload(async_median=0.80)),
        _histogram(),
    )

    assert weighted["weighted_serial_median_ms"] == pytest.approx(1.0)
    assert weighted["implementation_gate_max_async_ms"] == pytest.approx(0.90)
    assert weighted["weighted_async_median_ms"] < 0.90
    assert weighted["decision"] == "ASYNC_OVERLAP_MEASURED_GO"


def test_weight_async_records_complexity_no_go():
    weighted = weight_async(
        validate_async_raw(_payload(async_median=0.95)),
        _histogram(),
    )

    assert weighted["weighted_async_median_ms"] > 0.90
    assert weighted["decision"] == "ASYNC_OVERLAP_COMPLEXITY_NO_GO"


def test_weight_async_rejects_histogram_count_mismatch():
    histogram = copy.deepcopy(_histogram())
    histogram["gpu_resident_experts_per_top4_histogram"]["4"] -= 1

    with pytest.raises(
        MixedResidencyOverlapBoundError,
        match="histogram count sum mismatch",
    ):
        weight_async(validate_async_raw(_payload()), histogram)
