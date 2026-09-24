from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


class CbEvalInterceptBoundError(ValueError):
    pass


_EXPECTED_EXPERTS = [1, 13, 17, 21]
_EXPECTED_TOKEN = 2167
_EXPECTED_SAMPLES = 81
_EXPECTED_WARMUP = 6
_EXPECTED_ORDER = "even_stock_cancel_odd_cancel_stock"
_EXPECTED_WEIGHT_TENSOR = "ffn_moe_weights_softmax-0"


def _finite_positive(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CbEvalInterceptBoundError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise CbEvalInterceptBoundError(
            f"{label} must be positive and finite"
        )
    return number


def _summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    p95_index = min(
        len(ordered) - 1,
        math.ceil(0.95 * len(ordered)) - 1,
    )
    return {
        "median_ms": ordered[len(ordered) // 2],
        "p95_ms": ordered[p95_index],
        "min_ms": ordered[0],
        "max_ms": ordered[-1],
        "mean_ms": sum(ordered) / len(ordered),
    }


def _validate_stats(payload: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise CbEvalInterceptBoundError(f"{label} must be an object")
    values = payload.get("samples_ms")
    if (
        not isinstance(values, list)
        or len(values) != _EXPECTED_SAMPLES
    ):
        raise CbEvalInterceptBoundError(
            f"{label}.samples_ms must contain {_EXPECTED_SAMPLES} values"
        )

    parsed = [
        _finite_positive(value, label=f"{label}.samples_ms")
        for value in values
    ]
    expected = _summary(parsed)
    for field, expected_value in expected.items():
        observed = _finite_positive(
            payload.get(field),
            label=f"{label}.{field}",
        )
        if not math.isclose(
            observed,
            expected_value,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise CbEvalInterceptBoundError(
                f"{label}.{field} does not match samples"
            )

    return {
        **expected,
        "samples_ms": parsed,
    }


def validate_cb_eval_intercept_bound(
    payload: dict[str, Any],
) -> dict[str, Any]:
    if payload.get("schema") != "tesy.cb_eval_intercept_bound.v1":
        raise CbEvalInterceptBoundError("schema mismatch")
    if (
        payload.get("classification")
        != "MEASURED_CB_EVAL_ZERO_WORK_LOWER_BOUND"
    ):
        raise CbEvalInterceptBoundError("classification mismatch")

    expected_fields = {
        "layer": 0,
        "ngl": 0,
        "decode_input_token": _EXPECTED_TOKEN,
        "warmup_pairs": _EXPECTED_WARMUP,
        "sample_pairs": _EXPECTED_SAMPLES,
        "paired_order": _EXPECTED_ORDER,
        "route_weight_tensor": _EXPECTED_WEIGHT_TENSOR,
        "selected_experts": _EXPECTED_EXPERTS,
    }
    for field, expected in expected_fields.items():
        if payload.get(field) != expected:
            raise CbEvalInterceptBoundError(
                f"{field} mismatch: {payload.get(field)!r}"
            )

    weights = payload.get("routing_weights")
    if not isinstance(weights, list) or len(weights) != 4:
        raise CbEvalInterceptBoundError(
            "routing_weights must contain four values"
        )
    parsed_weights: list[float] = []
    for value in weights:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CbEvalInterceptBoundError(
                "routing_weights must be numeric"
            )
        number = float(value)
        if not math.isfinite(number) or number < 0.0:
            raise CbEvalInterceptBoundError(
                "routing_weights must be finite and non-negative"
            )
        parsed_weights.append(number)

    stock = _validate_stats(
        payload.get("stock_moe_segment"),
        label="stock_moe_segment",
    )
    cancel = _validate_stats(
        payload.get("cancel_zero_work"),
        label="cancel_zero_work",
    )

    median_ratio = cancel["median_ms"] / stock["median_ms"]
    p95_ratio = cancel["p95_ms"] / stock["p95_ms"]
    median_no_go = cancel["median_ms"] >= stock["median_ms"]
    p95_no_go = cancel["p95_ms"] >= stock["p95_ms"]
    decision = (
        "CB_EVAL_INTERCEPT_HARD_NO_GO"
        if median_no_go or p95_no_go
        else "CB_EVAL_INTERCEPT_BOUND_SURVIVES"
    )

    if payload.get("median_hard_no_go") is not median_no_go:
        raise CbEvalInterceptBoundError(
            "median_hard_no_go does not match samples"
        )
    if payload.get("p95_hard_no_go") is not p95_no_go:
        raise CbEvalInterceptBoundError(
            "p95_hard_no_go does not match samples"
        )
    if payload.get("decision") != decision:
        raise CbEvalInterceptBoundError(
            "decision does not match hard-bound inequalities"
        )

    for field, expected in (
        ("cancel_to_stock_median_ratio", median_ratio),
        ("cancel_to_stock_p95_ratio", p95_ratio),
    ):
        observed = _finite_positive(
            payload.get(field),
            label=field,
        )
        if not math.isclose(
            observed,
            expected,
            rel_tol=1e-9,
            abs_tol=1e-9,
        ):
            raise CbEvalInterceptBoundError(
                f"{field} does not match samples"
            )

    return {
        "schema": "tesy.cb_eval_intercept_bound_summary.v1",
        "classification": "MEASURED_CB_EVAL_INTERCEPT_FEASIBILITY_BOUND",
        "status": "PASS",
        "decision": decision,
        "decode_input_token": _EXPECTED_TOKEN,
        "selected_experts": _EXPECTED_EXPERTS,
        "routing_weights": parsed_weights,
        "stock_median_ms": stock["median_ms"],
        "stock_p95_ms": stock["p95_ms"],
        "cancel_median_ms": cancel["median_ms"],
        "cancel_p95_ms": cancel["p95_ms"],
        "cancel_to_stock_median_ratio": median_ratio,
        "cancel_to_stock_p95_ratio": p95_ratio,
        "median_hard_no_go": median_no_go,
        "p95_hard_no_go": p95_no_go,
        "claim_boundary": (
            "Measured zero-Tesy-work lower bound for external cb_eval "
            "interception on one repeated stock layer-0 route. A hard NO_GO "
            "means cancellation overhead alone cannot satisfy non-regression "
            "against the stock MoE segment on median or p95. A surviving "
            "bound only authorizes a full handoff experiment; it is not "
            "Tesy routed-layer performance."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to replace {args.output}")

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("cancel-bound input must be a JSON object")

    result = validate_cb_eval_intercept_bound(payload)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
