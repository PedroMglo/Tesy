import copy

import pytest

from tesy.routed_layer_exactness import (
    RoutedLayerExactnessError,
    validate_routed_layer_exactness,
)


def _tokens(values=None):
    return {
        "schema": "tesy.routed_layer_capture_tokens.v1",
        "classification": "MEASURED_GREEDY_TOKEN_IDS",
        "tokens": [101, 202] if values is None else values,
    }


def _capture():
    return {
        "schema": "tesy.routed_layer_capture.v1",
        "classification": "MEASURED_STOCK_ROUTED_LAYER_CAPTURE",
        "layer": 0,
        "phase": "decode",
        "n_embd": 2880,
        "n_expert_used": 4,
        "decode_input_token": 101,
        "decode_output_token": 202,
        "activation_tensor": "attn_post_norm-0",
        "topk_tensor": "ffn_moe_topk-0",
        "routing_weight_tensor": "ffn_moe_weights_softmax-0",
        "stock_output_tensor": "ffn_moe_out-0",
        "selected_experts": [7, 3, 21, 11],
        "routing_weights": [0.4, 0.3, 0.2, 0.1],
        "activation_file": "activation.f32",
        "stock_output_file": "stock-output.f32",
    }


def _parity():
    return {
        "max_abs": 1e-6,
        "max_abs_ref": 2.0,
        "relative_max": 5e-7,
        "cosine": 0.999999,
        "status": "PASS",
    }


def _replay(h):
    return {
        "schema": "tesy.routed_layer_exactness_raw.v1",
        "classification": "MEASURED_ROUTED_LAYER_REPLAY_EXACTNESS",
        "layer": 0,
        "gpu_hits": h,
        "cpu_misses": 4 - h,
        "controlled_partition": "TOPK_SLOT_PREFIX_GPU_REMAINDER_CPU",
        "cpu_weight_buffer_type": "CPU",
        "cpu_bias_buffer_type": "CPU",
        "selected_experts": [7, 3, 21, 11],
        "routing_weights": [0.4, 0.3, 0.2, 0.1],
        "serial_vs_stock": _parity(),
        "async_vs_stock": _parity(),
        "async_vs_serial": _parity(),
        "parity_thresholds": {
            "relative_max_max": 0.005,
            "cosine_min": 0.9999,
        },
    }


def _validate(
    *,
    capture=None,
    off=None,
    on=None,
    h2=None,
    h3=None,
):
    return validate_routed_layer_exactness(
        capture_metadata=_capture() if capture is None else capture,
        off_tokens=_tokens() if off is None else off,
        on_tokens=_tokens() if on is None else on,
        replay_h2=_replay(2) if h2 is None else h2,
        replay_h3=_replay(3) if h3 is None else h3,
    )


def test_routed_layer_exactness_accepts_exact_stock_capture_and_replays():
    result = _validate()

    assert result["status"] == "PASS"
    assert result["decision"] == "ROUTED_LAYER_EXACTNESS_GO"
    assert result["selected_experts"] == [7, 3, 21, 11]
    assert result["routing_weights"] == [0.4, 0.3, 0.2, 0.1]
    assert {row["gpu_hits"] for row in result["cases"]} == {2, 3}


def test_routed_layer_exactness_rejects_callback_token_mismatch():
    with pytest.raises(
        RoutedLayerExactnessError,
        match="greedy token IDs differ",
    ):
        _validate(on=_tokens([101, 203]))


def test_routed_layer_exactness_binds_capture_to_decode_tokens():
    capture = _capture()
    capture["decode_input_token"] = 999

    with pytest.raises(
        RoutedLayerExactnessError,
        match="decode input token",
    ):
        _validate(capture=capture)


def test_routed_layer_exactness_rejects_replay_expert_mutation():
    h2 = _replay(2)
    h2["selected_experts"] = [7, 3, 21, 12]

    with pytest.raises(
        RoutedLayerExactnessError,
        match="selected experts differ",
    ):
        _validate(h2=h2)


def test_routed_layer_exactness_rejects_replay_weight_mutation():
    h3 = _replay(3)
    h3["routing_weights"] = [0.4, 0.3, 0.1, 0.2]

    with pytest.raises(
        RoutedLayerExactnessError,
        match="routing weights differ",
    ):
        _validate(h3=h3)


def test_routed_layer_exactness_rejects_stock_parity_failure():
    h2 = _replay(2)
    h2["async_vs_stock"]["relative_max"] = 0.006

    with pytest.raises(
        RoutedLayerExactnessError,
        match="relative_max threshold",
    ):
        _validate(h2=h2)


def test_routed_layer_exactness_rejects_partition_policy_change():
    h2 = _replay(2)
    h2["controlled_partition"] = "ARBITRARY_CACHE_POLICY"

    with pytest.raises(
        RoutedLayerExactnessError,
        match="controlled partition",
    ):
        _validate(h2=h2)


def test_routed_layer_exactness_accepts_scaled_final_routing_weights():
    capture = _capture()
    capture["routing_weight_tensor"] = "ffn_moe_weights_scaled-0"

    result = _validate(capture=capture)

    assert result["routing_weight_tensor"] == "ffn_moe_weights_scaled-0"


def test_routed_layer_exactness_rejects_nonfinal_weight_tensor():
    capture = _capture()
    capture["routing_weight_tensor"] = "ffn_moe_weights-0"

    with pytest.raises(
        RoutedLayerExactnessError,
        match="unexpected routing weight tensor",
    ):
        _validate(capture=capture)


def test_routed_layer_exactness_rejects_duplicate_router_experts():
    capture = _capture()
    capture["selected_experts"] = [7, 3, 7, 11]

    with pytest.raises(
        RoutedLayerExactnessError,
        match="four unique IDs",
    ):
        _validate(capture=capture)


def test_routed_layer_exactness_rejects_threshold_drift():
    h3 = copy.deepcopy(_replay(3))
    h3["parity_thresholds"]["relative_max_max"] = 0.01

    with pytest.raises(
        RoutedLayerExactnessError,
        match="threshold contract mismatch",
    ):
        _validate(h3=h3)
