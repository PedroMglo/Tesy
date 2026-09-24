import copy

import pytest

from tesy.live_moe_handoff_timing import (
    LiveMoeHandoffTimingError,
    validate_live_moe_handoff_timing,
)


def _parity() -> dict:
    return {
        "max_abs": 1e-7,
        "max_abs_ref": 2.0,
        "relative_max": 5e-8,
        "cosine": 1.0,
        "status": "PASS",
    }


def _exactness() -> dict:
    return {
        "stock_decode_return_code": 0,
        "handoff_decode_return_code": 0,
        "stock_rollback": True,
        "handoff_rollback": True,
        "activation_bitwise_equal": True,
        "activation_parity": _parity(),
        "activation_vs_reference": _parity(),
        "stock_output_vs_reference": _parity(),
        "serial_vs_stock": _parity(),
        "async_vs_stock": _parity(),
        "async_vs_serial": _parity(),
    }


def _samples(value: float) -> list[float]:
    return [value] * 81


def _mode(activation: float, route: float) -> dict:
    return {
        "activation_ready_ms": _samples(activation),
        "route_ready_ms": _samples(route),
    }


def _raw(
    h: int,
    *,
    stock_activation: float = 3.0,
    stock_route: float = 2.7,
    serial_activation: float = 1.2,
    serial_route: float = 0.9,
    async_activation: float = 0.9,
    async_route: float = 0.6,
) -> dict:
    return {
        "schema": "tesy.live_moe_handoff_timing_raw.v1",
        "classification": "MEASURED_LIVE_MOE_HANDOFF_TIMING_RAW",
        "layer": 0,
        "ngl": 0,
        "gpu_hits": h,
        "cpu_misses": 4 - h,
        "threads": 12,
        "warmup_triplets": 6,
        "sample_triplets": 81,
        "inner": 1,
        "resident_experts": True,
        "provenance_gate": "FILE_EXISTENCE_BEFORE_WARMUP",
        "input_semantics": "HOST_CAPTURE_TO_CPU_AND_GPU_COMPACT_INPUTS",
        "decode_input_token": 2167,
        "activation_tensor": "attn_post_norm-0",
        "topk_tensor": "ffn_moe_topk-0",
        "routing_weight_tensor": "ffn_moe_weights_softmax-0",
        "stock_output_tensor": "ffn_moe_out-0",
        "selected_experts": [1, 13, 17, 21],
        "routing_weights": [0.4, 0.3, 0.2, 0.1],
        "completed_trials": {
            "stock": 87,
            "serial": 87,
            "async": 87,
        },
        "successful_rollbacks": 261,
        "triplet_order_cycle": [
            ["stock", "serial", "async"],
            ["stock", "async", "serial"],
            ["serial", "stock", "async"],
            ["serial", "async", "stock"],
            ["async", "stock", "serial"],
            ["async", "serial", "stock"],
        ],
        "pre_exactness": _exactness(),
        "post_exactness": _exactness(),
        "modes": {
            "stock": _mode(stock_activation, stock_route),
            "serial": _mode(serial_activation, serial_route),
            "async": _mode(async_activation, async_route),
        },
        "parity_thresholds": {
            "relative_max_max": 0.005,
            "cosine_min": 0.9999,
        },
    }


def test_live_timing_async_go_and_budget():
    result = validate_live_moe_handoff_timing(
        _raw(2),
        _raw(3),
    )

    assert result["decision"] == "LIVE_MOE_HANDOFF_TIMING_GO"
    assert result["chosen_execution"] == "async"
    assert result["reinjection_budget"]["route_median_min_ms"] == pytest.approx(
        2.1
    )
    assert result["reinjection_budget"]["route_p95_min_ms"] == pytest.approx(
        2.1
    )


def test_live_timing_serial_pivot_when_async_loses_overlap():
    h2 = _raw(2, async_route=1.0)
    h3 = _raw(3, async_route=1.0)

    result = validate_live_moe_handoff_timing(h2, h3)

    assert result["decision"] == "LIVE_MOE_HANDOFF_TIMING_SERIAL_PIVOT"
    assert result["chosen_execution"] == "serial"
    assert result["reinjection_budget"]["route_median_min_ms"] == pytest.approx(
        1.8
    )


def test_live_timing_no_go_when_neither_path_beats_stock():
    h2 = _raw(
        2,
        serial_activation=3.1,
        serial_route=2.8,
        async_activation=3.2,
        async_route=2.9,
    )
    h3 = _raw(
        3,
        serial_activation=3.1,
        serial_route=2.8,
        async_activation=3.2,
        async_route=2.9,
    )

    result = validate_live_moe_handoff_timing(h2, h3)

    assert result["decision"] == "LIVE_MOE_HANDOFF_TIMING_NO_GO"
    assert result["chosen_execution"] == "none"
    assert result["reinjection_budget"]["route_median_min_ms"] is None


def test_live_timing_p95_failure_blocks_async_go():
    h2 = _raw(2)
    h3 = _raw(3)

    for raw in (h2, h3):
        values = raw["modes"]["async"]["route_ready_ms"]
        for index in range(76, 81):
            values[index] = 3.0

    result = validate_live_moe_handoff_timing(h2, h3)

    assert result["decision"] == "LIVE_MOE_HANDOFF_TIMING_SERIAL_PIVOT"
    assert all(
        not row["async_survives_stock"]
        for row in result["cases"]
    )


def test_live_timing_rejects_sample_count_drift():
    h2 = _raw(2)
    h2["modes"]["async"]["route_ready_ms"].pop()

    with pytest.raises(
        LiveMoeHandoffTimingError,
        match="must contain 81 values",
    ):
        validate_live_moe_handoff_timing(h2, _raw(3))


def test_live_timing_rejects_post_exactness_failure():
    h3 = _raw(3)
    h3["post_exactness"]["async_vs_stock"]["relative_max"] = 0.01

    with pytest.raises(
        LiveMoeHandoffTimingError,
        match="post_exactness.async_vs_stock relative_max",
    ):
        validate_live_moe_handoff_timing(_raw(2), h3)


def test_live_timing_rejects_routing_weight_mismatch_between_h():
    h3 = _raw(3)
    h3["routing_weights"][0] = 0.41

    with pytest.raises(
        LiveMoeHandoffTimingError,
        match="routing weights differ",
    ):
        validate_live_moe_handoff_timing(_raw(2), h3)


def test_live_timing_rejects_completed_trial_drift():
    h2 = _raw(2)
    h2["completed_trials"]["async"] = 86

    with pytest.raises(
        LiveMoeHandoffTimingError,
        match="completed_trials mismatch",
    ):
        validate_live_moe_handoff_timing(h2, _raw(3))


def test_live_timing_rejects_nonpositive_sample():
    h2 = _raw(2)
    h2["modes"]["stock"]["activation_ready_ms"][0] = 0.0

    with pytest.raises(
        LiveMoeHandoffTimingError,
        match="must be positive",
    ):
        validate_live_moe_handoff_timing(h2, _raw(3))


def test_live_timing_rejects_threshold_drift():
    h2 = copy.deepcopy(_raw(2))
    h2["parity_thresholds"]["relative_max_max"] = 0.01

    with pytest.raises(
        LiveMoeHandoffTimingError,
        match="parity_thresholds mismatch",
    ):
        validate_live_moe_handoff_timing(h2, _raw(3))


def test_live_timing_rejects_provenance_gate_drift():
    h2 = _raw(2)
    h2["provenance_gate"] = "NONE"

    with pytest.raises(
        LiveMoeHandoffTimingError,
        match="provenance_gate mismatch",
    ):
        validate_live_moe_handoff_timing(h2, _raw(3))
