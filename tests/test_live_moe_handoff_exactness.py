import copy

import pytest

from tesy.live_moe_handoff_exactness import (
    LiveMoeHandoffExactnessError,
    validate_live_moe_handoff_exactness,
)


def _parity() -> dict:
    return {
        "max_abs": 1e-7,
        "max_abs_ref": 2.0,
        "relative_max": 5e-8,
        "cosine": 1.0,
        "status": "PASS",
    }


def _case(h: int) -> dict:
    return {
        "gpu_hits": h,
        "cpu_misses": 4 - h,
        "serial_vs_stock": _parity(),
        "async_vs_stock": _parity(),
        "async_vs_serial": _parity(),
    }


def _payload() -> dict:
    return {
        "schema": "tesy.live_moe_handoff_exactness.v1",
        "classification": "MEASURED_LIVE_MOE_HANDOFF_EXACTNESS",
        "layer": 0,
        "ngl": 0,
        "decode_input_token": 2167,
        "stock_decode_return_code": 0,
        "handoff_decode_return_code": 0,
        "stock_rollback": True,
        "handoff_rollback": True,
        "activation_tensor": "attn_post_norm-0",
        "topk_tensor": "ffn_moe_topk-0",
        "routing_weight_tensor": "ffn_moe_weights_softmax-0",
        "stock_output_tensor": "ffn_moe_out-0",
        "activation_bitwise_equal": True,
        "activation_parity": _parity(),
        "selected_experts": [1, 13, 17, 21],
        "routing_weights": [0.4, 0.3, 0.2, 0.1],
        "cases": [_case(2), _case(3)],
        "parity_thresholds": {
            "relative_max_max": 0.005,
            "cosine_min": 0.9999,
        },
        "decision": "LIVE_MOE_HANDOFF_EXACTNESS_GO",
    }


def test_live_handoff_accepts_exactness_only_result():
    result = validate_live_moe_handoff_exactness(_payload())

    assert result["status"] == "PASS"
    assert result["decision"] == "LIVE_MOE_HANDOFF_EXACTNESS_GO"
    assert result["selected_experts"] == [1, 13, 17, 21]
    assert {row["gpu_hits"] for row in result["cases"]} == {2, 3}


def test_live_handoff_does_not_require_bitwise_activation():
    payload = _payload()
    payload["activation_bitwise_equal"] = False

    result = validate_live_moe_handoff_exactness(payload)

    assert result["activation_bitwise_equal"] is False
    assert result["activation_parity"]["status"] == "PASS"


def test_live_handoff_rejects_wrong_decode_token():
    payload = _payload()
    payload["decode_input_token"] = 999

    with pytest.raises(
        LiveMoeHandoffExactnessError,
        match="decode_input_token mismatch",
    ):
        validate_live_moe_handoff_exactness(payload)


def test_live_handoff_rejects_failed_rollback():
    payload = _payload()
    payload["handoff_rollback"] = False

    with pytest.raises(
        LiveMoeHandoffExactnessError,
        match="handoff_rollback mismatch",
    ):
        validate_live_moe_handoff_exactness(payload)


def test_live_handoff_rejects_route_drift():
    payload = _payload()
    payload["selected_experts"] = [1, 13, 17, 20]

    with pytest.raises(
        LiveMoeHandoffExactnessError,
        match="selected_experts mismatch",
    ):
        validate_live_moe_handoff_exactness(payload)


def test_live_handoff_rejects_activation_parity_failure():
    payload = _payload()
    payload["activation_parity"]["relative_max"] = 0.006

    with pytest.raises(
        LiveMoeHandoffExactnessError,
        match="activation_parity relative_max",
    ):
        validate_live_moe_handoff_exactness(payload)


def test_live_handoff_rejects_async_stock_parity_failure():
    payload = _payload()
    payload["cases"][1]["async_vs_stock"]["cosine"] = 0.99

    with pytest.raises(
        LiveMoeHandoffExactnessError,
        match="h3.async_vs_stock cosine",
    ):
        validate_live_moe_handoff_exactness(payload)


def test_live_handoff_requires_h2_and_h3_once_each():
    payload = _payload()
    payload["cases"] = [_case(2), _case(2)]

    with pytest.raises(
        LiveMoeHandoffExactnessError,
        match="unique gpu_hits 2 and 3",
    ):
        validate_live_moe_handoff_exactness(payload)


def test_live_handoff_rejects_timing_fields():
    payload = _payload()
    payload["cases"][0]["median_ms"] = 1.0

    with pytest.raises(
        LiveMoeHandoffExactnessError,
        match="timing field forbidden",
    ):
        validate_live_moe_handoff_exactness(payload)


def test_live_handoff_rejects_threshold_drift():
    payload = copy.deepcopy(_payload())
    payload["parity_thresholds"]["relative_max_max"] = 0.01

    with pytest.raises(
        LiveMoeHandoffExactnessError,
        match="parity_thresholds mismatch",
    ):
        validate_live_moe_handoff_exactness(payload)


def test_live_handoff_rejects_premature_decision_change():
    payload = _payload()
    payload["decision"] = "LIVE_MOE_HANDOFF_TIMING_GO"

    with pytest.raises(
        LiveMoeHandoffExactnessError,
        match="decision mismatch",
    ):
        validate_live_moe_handoff_exactness(payload)
