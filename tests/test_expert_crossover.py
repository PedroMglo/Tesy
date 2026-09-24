import copy

import pytest

from tesy.expert_crossover import ExpertCrossoverError, validate_expert_crossover


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


def _row(k: int, pinned: bool = True) -> dict:
    cpu = _stats(3.0 * k)
    gpu = _stats(0.5 * k)
    d2h = _stats(0.10)
    h2d = _stats(0.11)
    weight = _stats(2.0 * k)
    pinned_stats = _stats(1.5 * k) if pinned else None
    return {
        "k": k,
        "source_expert_ids": list(range(k)),
        "requested_weight_bytes": 13_253_760 * k,
        "activation_input_bytes": 11_520,
        "activation_output_bytes": 11_520,
        "cpu_weight_buffer_type": "CPU",
        "cpu_weight_buffer_bytes": 13_220_000 * k,
        "cpu_bias_buffer_bytes": 40_000 * k,
        "cpu_compute": cpu,
        "gpu_compute": gpu,
        "activation_d2h": d2h,
        "activation_h2d": h2d,
        "weight_h2d_pageable": weight,
        "pinned_available": pinned,
        "weight_h2d_pinned": pinned_stats,
        "parity": {
            "max_abs": 0.001,
            "max_abs_ref": 2.0,
            "relative_max": 0.0005,
            "cosine": 0.99999,
            "status": "PASS",
        },
        "derived": {
            "cpu_path_median_ms": (
                d2h["median_ms"] + cpu["median_ms"] + h2d["median_ms"]
            ),
            "cold_gpu_pageable_median_ms": (
                weight["median_ms"] + gpu["median_ms"]
            ),
            "cold_gpu_pinned_median_ms": (
                pinned_stats["median_ms"] + gpu["median_ms"]
                if pinned_stats is not None
                else None
            ),
            "resident_gpu_median_ms": gpu["median_ms"],
        },
    }


def _payload() -> dict:
    return {
        "schema": "tesy.expert_crossover_raw.v1",
        "classification": "MEASURED_EXPERT_CROSSOVER_MICROBENCHMARK",
        "layer": 0,
        "threads": 12,
        "warmup": 3,
        "samples": 5,
        "compute_inner": 5,
        "transfer_inner": 4,
        "activation_inner": 100,
        "n_embd": 2880,
        "expert_count_model": 32,
        "encoded_bytes_per_expert": 13_253_760,
        "weight_type": "mxfp4",
        "bias_type": "f32",
        "weight_shape": [2880, 2880, 32],
        "bias_shape": [2880, 32],
        "cpu_device": "CPU",
        "gpu_device": "GPU",
        "results": [_row(1), _row(4)],
        "claim_boundary": "requested bytes only",
    }


def test_validate_expert_crossover_accepts_frozen_contract():
    result = validate_expert_crossover(_payload())
    assert result["status"] == "PASS"
    assert [row["k"] for row in result["results"]] == [1, 4]
    assert result["results"][1]["requested_weight_bytes"] == 53_015_040


def test_validate_expert_crossover_accepts_missing_pinned_path():
    payload = _payload()
    payload["results"][0] = _row(1, pinned=False)
    result = validate_expert_crossover(payload)
    assert result["results"][0]["median_ms"]["cold_gpu_pinned"] is None


def test_validate_expert_crossover_rejects_wrong_requested_bytes():
    payload = _payload()
    payload["results"][1]["requested_weight_bytes"] += 1
    with pytest.raises(ExpertCrossoverError, match="requested weight bytes mismatch"):
        validate_expert_crossover(payload)


def test_validate_expert_crossover_rejects_failed_parity():
    payload = _payload()
    payload["results"][0]["parity"]["status"] = "FAIL"
    with pytest.raises(ExpertCrossoverError, match="parity did not PASS"):
        validate_expert_crossover(payload)


def test_validate_expert_crossover_rejects_derived_path_tampering():
    payload = copy.deepcopy(_payload())
    payload["results"][0]["derived"]["cpu_path_median_ms"] += 1.0
    with pytest.raises(ExpertCrossoverError, match="derived path mismatch"):
        validate_expert_crossover(payload)


def test_validate_expert_crossover_rejects_non_authoritative_cpu_buffer():
    payload = _payload()
    payload["results"][0]["cpu_weight_buffer_type"] = "CPU_REPACK"
    with pytest.raises(ExpertCrossoverError, match="expected CPU default buffer"):
        validate_expert_crossover(payload)
