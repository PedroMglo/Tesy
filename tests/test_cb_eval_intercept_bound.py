import copy

import pytest

from tesy.cb_eval_intercept_bound import (
    CbEvalInterceptBoundError,
    validate_cb_eval_intercept_bound,
)


def _stats(value: float) -> dict:
    samples = [value] * 81
    return {
        "median_ms": value,
        "p95_ms": value,
        "min_ms": value,
        "max_ms": value,
        "mean_ms": value,
        "samples_ms": samples,
    }


def _payload(
    *,
    stock: float = 0.50,
    cancel: float = 0.20,
) -> dict:
    return {
        "schema": "tesy.cb_eval_intercept_bound.v1",
        "classification": "MEASURED_CB_EVAL_ZERO_WORK_LOWER_BOUND",
        "layer": 0,
        "ngl": 0,
        "decode_input_token": 2167,
        "warmup_pairs": 6,
        "sample_pairs": 81,
        "paired_order": "even_stock_cancel_odd_cancel_stock",
        "route_weight_tensor": "ffn_moe_weights_softmax-0",
        "selected_experts": [1, 13, 17, 21],
        "routing_weights": [0.4, 0.3, 0.2, 0.1],
        "stock_moe_segment": _stats(stock),
        "cancel_zero_work": _stats(cancel),
        "cancel_to_stock_median_ratio": cancel / stock,
        "cancel_to_stock_p95_ratio": cancel / stock,
        "median_hard_no_go": cancel >= stock,
        "p95_hard_no_go": cancel >= stock,
        "decision": (
            "CB_EVAL_INTERCEPT_HARD_NO_GO"
            if cancel >= stock
            else "CB_EVAL_INTERCEPT_BOUND_SURVIVES"
        ),
    }


def test_cb_eval_bound_survives_only_as_feasibility_bound():
    result = validate_cb_eval_intercept_bound(_payload())

    assert result["status"] == "PASS"
    assert result["decision"] == "CB_EVAL_INTERCEPT_BOUND_SURVIVES"
    assert result["median_hard_no_go"] is False
    assert result["p95_hard_no_go"] is False


def test_cb_eval_bound_hard_no_go_on_p95_only():
    payload = _payload(stock=0.50, cancel=0.20)
    values = payload["cancel_zero_work"]["samples_ms"]
    for index in range(77, 81):
        values[index] = 0.60
    values.sort()
    payload["cancel_zero_work"]["median_ms"] = values[40]
    payload["cancel_zero_work"]["p95_ms"] = values[77]
    payload["cancel_zero_work"]["max_ms"] = values[-1]
    payload["cancel_zero_work"]["mean_ms"] = sum(values) / len(values)
    payload["cancel_to_stock_median_ratio"] = (
        payload["cancel_zero_work"]["median_ms"] / 0.50
    )
    payload["cancel_to_stock_p95_ratio"] = (
        payload["cancel_zero_work"]["p95_ms"] / 0.50
    )
    payload["median_hard_no_go"] = False
    payload["p95_hard_no_go"] = True
    payload["decision"] = "CB_EVAL_INTERCEPT_HARD_NO_GO"

    result = validate_cb_eval_intercept_bound(payload)

    assert result["decision"] == "CB_EVAL_INTERCEPT_HARD_NO_GO"
    assert result["median_hard_no_go"] is False
    assert result["p95_hard_no_go"] is True

def test_cb_eval_bound_hard_no_go_when_cancel_equals_stock():
    result = validate_cb_eval_intercept_bound(
        _payload(stock=0.50, cancel=0.50)
    )

    assert result["decision"] == "CB_EVAL_INTERCEPT_HARD_NO_GO"
    assert result["median_hard_no_go"] is True
    assert result["p95_hard_no_go"] is True


def test_cb_eval_bound_rejects_wrong_route_identity():
    payload = _payload()
    payload["selected_experts"] = [1, 13, 17, 20]

    with pytest.raises(
        CbEvalInterceptBoundError,
        match="selected_experts mismatch",
    ):
        validate_cb_eval_intercept_bound(payload)


def test_cb_eval_bound_rejects_wrong_decode_token():
    payload = _payload()
    payload["decode_input_token"] = 999

    with pytest.raises(
        CbEvalInterceptBoundError,
        match="decode_input_token mismatch",
    ):
        validate_cb_eval_intercept_bound(payload)


def test_cb_eval_bound_rejects_sample_count_drift():
    payload = _payload()
    payload["cancel_zero_work"]["samples_ms"].pop()

    with pytest.raises(
        CbEvalInterceptBoundError,
        match="must contain 81 values",
    ):
        validate_cb_eval_intercept_bound(payload)


def test_cb_eval_bound_recomputes_decision():
    payload = _payload(stock=0.50, cancel=0.50)
    payload["decision"] = "CB_EVAL_INTERCEPT_BOUND_SURVIVES"

    with pytest.raises(
        CbEvalInterceptBoundError,
        match="decision does not match",
    ):
        validate_cb_eval_intercept_bound(payload)


def test_cb_eval_bound_rejects_summary_not_matching_samples():
    payload = _payload()
    payload["cancel_zero_work"]["median_ms"] = 0.21

    with pytest.raises(
        CbEvalInterceptBoundError,
        match="median_ms does not match samples",
    ):
        validate_cb_eval_intercept_bound(payload)


def test_cb_eval_bound_rejects_ratio_drift():
    payload = copy.deepcopy(_payload())
    payload["cancel_to_stock_median_ratio"] = 0.9

    with pytest.raises(
        CbEvalInterceptBoundError,
        match="cancel_to_stock_median_ratio",
    ):
        validate_cb_eval_intercept_bound(payload)
