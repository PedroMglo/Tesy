import copy

import pytest

from tesy.mixed_residency_overlap_bound import (
    MixedResidencyOverlapBoundError,
    validate_overlap_bound_raw,
    weight_overlap_bound,
)


def _stats(base: float) -> dict:
    samples = [base + i * 0.01 for i in range(5)]
    return {
        "median_ms": samples[2],
        "p95_ms": samples[-1],
        "min_ms": samples[0],
        "max_ms": samples[-1],
        "mean_ms": sum(samples) / len(samples),
        "samples_ms": samples,
    }


def _case(h: int) -> dict:
    cpu = 4 - h
    d2h = _stats(0.01) if cpu else None
    cpu_compute = _stats(0.6 * cpu / 4) if cpu else None
    gpu_compute = _stats(0.25 * h / 4) if h else None
    h2d = _stats(0.01) if cpu else None
    agg = _stats(0.03) if 0 < h < 4 else None

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
        bound = component_sum
    else:
        component_sum = gpu_compute["median_ms"]
        bound = component_sum

    direct = _stats(component_sum + 0.05)
    return {
        "gpu_hits": h,
        "cpu_misses": cpu,
        "source_expert_ids": [0, 1, 2, 3],
        "global_mix_weight": 0.25,
        "direct_wall": direct,
        "components": {
            "activation_d2h": d2h,
            "cpu_compute": cpu_compute,
            "gpu_compute": gpu_compute,
            "cpu_partial_h2d": h2d,
            "gpu_aggregation": agg,
        },
        "component_sum_median_ms": component_sum,
        "post_d2h_overlap_bound_median_ms": bound,
        "overlap_bound_speedup_vs_direct": direct["median_ms"] / bound,
        "parity": {
            "max_abs": 0.001,
            "max_abs_ref": 2.0,
            "relative_max": 0.0005,
            "cosine": 0.99999,
            "status": "PASS",
        },
    }


def _payload() -> dict:
    return {
        "schema": "tesy.mixed_residency_overlap_bound_raw.v1",
        "classification": "MEASURED_MIXED_RESIDENCY_COMPONENT_DIAGNOSTIC",
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
        "expert_ids": [0, 1, 2, 3],
        "mix_weights": [0.25, 0.25, 0.25, 0.25],
        "measurement_order": [0, 4, 1, 3, 2],
        "cases": [_case(h) for h in range(5)],
        "claim_boundary": "component diagnostic",
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


def test_validate_overlap_bound_accepts_full_component_contract():
    summary = validate_overlap_bound_raw(_payload())

    assert summary["status"] == "PASS"
    assert [row["gpu_hits"] for row in summary["cases"]] == [0, 1, 2, 3, 4]
    assert summary["cases"][0]["dominating_compute_branch"] == "CPU_ONLY"
    assert summary["cases"][4]["dominating_compute_branch"] == "GPU_ONLY"
    assert summary["cases"][2]["overlap_bound_speedup_vs_direct"] > 1.0


def test_validate_overlap_bound_rejects_component_presence_mismatch():
    payload = _payload()
    payload["cases"][4]["components"]["activation_d2h"] = _stats(0.01)

    with pytest.raises(
        MixedResidencyOverlapBoundError,
        match="activation_d2h must be null",
    ):
        validate_overlap_bound_raw(payload)


def test_validate_overlap_bound_rejects_bound_tampering():
    payload = _payload()
    payload["cases"][2]["post_d2h_overlap_bound_median_ms"] += 0.1

    with pytest.raises(
        MixedResidencyOverlapBoundError,
        match="overlap bound mismatch",
    ):
        validate_overlap_bound_raw(payload)


def test_validate_overlap_bound_rejects_failed_parity():
    payload = _payload()
    payload["cases"][3]["parity"]["status"] = "FAIL"

    with pytest.raises(
        MixedResidencyOverlapBoundError,
        match="parity did not PASS",
    ):
        validate_overlap_bound_raw(payload)


def test_weight_overlap_bound_uses_admitted_group_counts():
    summary = validate_overlap_bound_raw(_payload())
    weighted = weight_overlap_bound(summary, _histogram())

    counts = [39, 26, 62, 128, 105]
    expected_direct = sum(
        counts[h] * summary["cases"][h]["direct_median_ms"]
        for h in range(5)
    ) / 360
    expected_bound = sum(
        counts[h] * summary["cases"][h]["post_d2h_overlap_bound_median_ms"]
        for h in range(5)
    ) / 360

    assert weighted["status"] == "PASS"
    assert weighted["weighted_direct_median_ms"] == pytest.approx(expected_direct)
    assert weighted["weighted_post_d2h_overlap_bound_ms"] == pytest.approx(
        expected_bound
    )
    assert weighted["bound_speedup_vs_weighted_direct"] > 1.0
    assert weighted["implementation_gate_ratio"] == 0.90
    assert weighted["implementation_gate_max_bound_ms"] == pytest.approx(
        0.90 * expected_direct
    )
    assert weighted["decision"] == "OVERLAP_IMPLEMENTATION_GO"


def test_weight_overlap_bound_records_complexity_no_go_below_threshold():
    summary = validate_overlap_bound_raw(_payload())
    histogram = _histogram()
    histogram["gpu_resident_experts_per_top4_histogram"] = {
        "0": 360,
        "1": 0,
        "2": 0,
        "3": 0,
        "4": 0,
    }

    weighted = weight_overlap_bound(summary, histogram)

    assert weighted["weighted_post_d2h_overlap_bound_ms"] > (
        weighted["implementation_gate_max_bound_ms"]
    )
    assert weighted["decision"] == "OVERLAP_COMPLEXITY_NO_GO"


def test_weight_overlap_bound_rejects_histogram_count_mismatch():
    histogram = copy.deepcopy(_histogram())
    histogram["gpu_resident_experts_per_top4_histogram"]["4"] -= 1

    with pytest.raises(
        MixedResidencyOverlapBoundError,
        match="histogram count sum mismatch",
    ):
        weight_overlap_bound(
            validate_overlap_bound_raw(_payload()),
            histogram,
        )
