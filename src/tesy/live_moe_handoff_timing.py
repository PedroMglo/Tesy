from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


class LiveMoeHandoffTimingError(ValueError):
    pass


def _no_duplicate_object(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LiveMoeHandoffTimingError(
                f"duplicate JSON key: {key}"
            )
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_no_duplicate_object,
    )


def _require_exact_keys(
    payload: dict[str, Any],
    *,
    expected: set[str],
    label: str,
) -> None:
    observed = set(payload)
    if observed != expected:
        raise LiveMoeHandoffTimingError(
            f"{label} keys mismatch: "
            f"missing={sorted(expected - observed)!r} "
            f"extra={sorted(observed - expected)!r}"
        )


_EXPECTED_TOKEN = 2167
_EXPECTED_EXPERTS = [1, 13, 17, 21]
_EXPECTED_THRESHOLDS = {
    "relative_max_max": 0.005,
    "cosine_min": 0.9999,
}
_EXPECTED_ORDER = [
    ["stock", "serial", "async"],
    ["stock", "async", "serial"],
    ["serial", "stock", "async"],
    ["serial", "async", "stock"],
    ["async", "stock", "serial"],
    ["async", "serial", "stock"],
]
_EXPECTED_WARMUP = 6
_EXPECTED_SAMPLES = 81
_EXPECTED_INNER = 1
_EXPECTED_COMPLETED = _EXPECTED_WARMUP + _EXPECTED_SAMPLES
_EXPECTED_ROLLBACKS = 3 * _EXPECTED_COMPLETED
_EXPECTED_ORDER_FULL_CYCLES = 13
_EXPECTED_ORDER_TAIL = [0, 3, 4]
_EXPECTED_ORDINAL_COUNTS = {
    "stock": [27, 27, 27],
    "serial": [27, 27, 27],
    "async": [27, 27, 27],
}


def _finite(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LiveMoeHandoffTimingError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise LiveMoeHandoffTimingError(f"{label} must be finite")
    return number


def _positive(value: Any, *, label: str) -> float:
    number = _finite(value, label=label)
    if number <= 0.0:
        raise LiveMoeHandoffTimingError(f"{label} must be positive")
    return number


def _stats(values: list[float]) -> dict[str, Any]:
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
        "samples_ms": values,
    }


def _parity(payload: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LiveMoeHandoffTimingError(f"{label} must be an object")
    _require_exact_keys(
        payload,
        expected={
            "max_abs",
            "max_abs_ref",
            "relative_max",
            "cosine",
            "status",
        },
        label=label,
    )
    if payload.get("status") != "PASS":
        raise LiveMoeHandoffTimingError(f"{label} did not PASS")

    relative = _finite(
        payload.get("relative_max"),
        label=f"{label}.relative_max",
    )
    cosine = _finite(
        payload.get("cosine"),
        label=f"{label}.cosine",
    )
    _finite(payload.get("max_abs"), label=f"{label}.max_abs")
    _finite(
        payload.get("max_abs_ref"),
        label=f"{label}.max_abs_ref",
    )

    if relative > _EXPECTED_THRESHOLDS["relative_max_max"]:
        raise LiveMoeHandoffTimingError(
            f"{label} relative_max threshold violated"
        )
    if cosine < _EXPECTED_THRESHOLDS["cosine_min"]:
        raise LiveMoeHandoffTimingError(
            f"{label} cosine threshold violated"
        )
    return payload


def _exactness(payload: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LiveMoeHandoffTimingError(f"{label} must be an object")
    _require_exact_keys(
        payload,
        expected={
            "stock_decode_return_code",
            "handoff_decode_return_code",
            "stock_rollback",
            "handoff_rollback",
            "activation_bitwise_equal",
            "activation_parity",
            "activation_vs_reference",
            "stock_output_vs_reference",
            "serial_vs_stock",
            "async_vs_stock",
            "async_vs_serial",
        },
        label=label,
    )

    expected = {
        "stock_decode_return_code": 0,
        "handoff_decode_return_code": 0,
        "stock_rollback": True,
        "handoff_rollback": True,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise LiveMoeHandoffTimingError(
                f"{label}.{field} mismatch"
            )

    bitwise = payload.get("activation_bitwise_equal")
    if not isinstance(bitwise, bool):
        raise LiveMoeHandoffTimingError(
            f"{label}.activation_bitwise_equal must be boolean"
        )

    result = {
        "stock_decode_return_code": 0,
        "handoff_decode_return_code": 0,
        "stock_rollback": True,
        "handoff_rollback": True,
        "activation_bitwise_equal": bitwise,
    }
    for field in (
        "activation_parity",
        "activation_vs_reference",
        "stock_output_vs_reference",
        "serial_vs_stock",
        "async_vs_stock",
        "async_vs_serial",
    ):
        result[field] = _parity(
            payload.get(field),
            label=f"{label}.{field}",
        )
    return result


def _mode(payload: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LiveMoeHandoffTimingError(f"{label} must be an object")
    _require_exact_keys(
        payload,
        expected={"activation_ready_ms", "route_ready_ms"},
        label=label,
    )

    result: dict[str, Any] = {}
    for field in ("activation_ready_ms", "route_ready_ms"):
        values = payload.get(field)
        if (
            not isinstance(values, list)
            or len(values) != _EXPECTED_SAMPLES
        ):
            raise LiveMoeHandoffTimingError(
                f"{label}.{field} must contain {_EXPECTED_SAMPLES} values"
            )
        parsed = [
            _positive(value, label=f"{label}.{field}")
            for value in values
        ]
        result[field] = _stats(parsed)
    return result


def _validate_raw(
    payload: dict[str, Any],
    *,
    expected_h: int,
) -> dict[str, Any]:
    _require_exact_keys(
        payload,
        expected={
            "schema",
            "classification",
            "layer",
            "ngl",
            "gpu_hits",
            "cpu_misses",
            "threads",
            "warmup_triplets",
            "sample_triplets",
            "inner",
            "resident_experts",
            "provenance_gate",
            "input_semantics",
            "decode_input_token",
            "activation_tensor",
            "topk_tensor",
            "routing_weight_tensor",
            "stock_output_tensor",
            "selected_experts",
            "routing_weights",
            "completed_trials",
            "successful_rollbacks",
            "triplet_order_cycle",
            "measured_order_full_cycles",
            "measured_order_tail_indices",
            "measured_ordinal_counts",
            "pre_exactness",
            "post_exactness",
            "modes",
            "parity_thresholds",
            "claim_boundary",
        },
        label=f"h={expected_h}",
    )
    if payload.get("schema") != "tesy.live_moe_handoff_timing_raw.v1":
        raise LiveMoeHandoffTimingError("schema mismatch")
    if (
        payload.get("classification")
        != "MEASURED_LIVE_MOE_HANDOFF_TIMING_RAW"
    ):
        raise LiveMoeHandoffTimingError("classification mismatch")

    expected = {
        "layer": 0,
        "ngl": 0,
        "gpu_hits": expected_h,
        "cpu_misses": 4 - expected_h,
        "threads": 12,
        "warmup_triplets": _EXPECTED_WARMUP,
        "sample_triplets": _EXPECTED_SAMPLES,
        "inner": _EXPECTED_INNER,
        "resident_experts": True,
        "provenance_gate": "FILE_EXISTENCE_BEFORE_WARMUP",
        "input_semantics": "HOST_CAPTURE_TO_CPU_AND_GPU_COMPACT_INPUTS",
        "decode_input_token": _EXPECTED_TOKEN,
        "activation_tensor": "attn_post_norm-0",
        "topk_tensor": "ffn_moe_topk-0",
        "routing_weight_tensor": "ffn_moe_weights_softmax-0",
        "stock_output_tensor": "ffn_moe_out-0",
        "selected_experts": _EXPECTED_EXPERTS,
        "triplet_order_cycle": _EXPECTED_ORDER,
        "measured_order_full_cycles": _EXPECTED_ORDER_FULL_CYCLES,
        "measured_order_tail_indices": _EXPECTED_ORDER_TAIL,
        "measured_ordinal_counts": _EXPECTED_ORDINAL_COUNTS,
        "parity_thresholds": _EXPECTED_THRESHOLDS,
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise LiveMoeHandoffTimingError(
                f"h={expected_h} {field} mismatch"
            )

    completed = payload.get("completed_trials")
    if not isinstance(completed, dict):
        raise LiveMoeHandoffTimingError(
            f"h={expected_h} completed_trials must be an object"
        )
    _require_exact_keys(
        completed,
        expected={"stock", "serial", "async"},
        label=f"h={expected_h}.completed_trials",
    )
    if completed != {
        "stock": _EXPECTED_COMPLETED,
        "serial": _EXPECTED_COMPLETED,
        "async": _EXPECTED_COMPLETED,
    }:
        raise LiveMoeHandoffTimingError(
            f"h={expected_h} completed_trials mismatch"
        )
    if payload.get("successful_rollbacks") != _EXPECTED_ROLLBACKS:
        raise LiveMoeHandoffTimingError(
            f"h={expected_h} successful_rollbacks mismatch"
        )

    weights = payload.get("routing_weights")
    if not isinstance(weights, list) or len(weights) != 4:
        raise LiveMoeHandoffTimingError(
            f"h={expected_h} routing_weights must contain four values"
        )
    parsed_weights: list[float] = []
    for value in weights:
        number = _finite(
            value,
            label=f"h={expected_h}.routing_weights",
        )
        if number < 0.0:
            raise LiveMoeHandoffTimingError(
                f"h={expected_h} routing_weights must be non-negative"
            )
        parsed_weights.append(number)

    modes = payload.get("modes")
    if not isinstance(modes, dict):
        raise LiveMoeHandoffTimingError(
            f"h={expected_h} modes must be an object"
        )
    _require_exact_keys(
        modes,
        expected={"stock", "serial", "async"},
        label=f"h={expected_h}.modes",
    )

    claim = payload.get("claim_boundary")
    if not isinstance(claim, str) or not claim:
        raise LiveMoeHandoffTimingError(
            f"h={expected_h} claim_boundary must be non-empty"
        )

    return {
        "gpu_hits": expected_h,
        "cpu_misses": 4 - expected_h,
        "routing_weights": parsed_weights,
        "pre_exactness": _exactness(
            payload.get("pre_exactness"),
            label=f"h={expected_h}.pre_exactness",
        ),
        "post_exactness": _exactness(
            payload.get("post_exactness"),
            label=f"h={expected_h}.post_exactness",
        ),
        "stock": _mode(
            modes.get("stock"),
            label=f"h={expected_h}.stock",
        ),
        "serial": _mode(
            modes.get("serial"),
            label=f"h={expected_h}.serial",
        ),
        "async": _mode(
            modes.get("async"),
            label=f"h={expected_h}.async",
        ),
    }


def _window_summary(
    row: dict[str, Any],
    *,
    field: str,
) -> dict[str, Any]:
    stock = row["stock"][field]
    serial = row["serial"][field]
    async_ = row["async"][field]
    return {
        "stock": stock,
        "serial": serial,
        "async": async_,
        "serial_budget_median_ms": (
            stock["median_ms"] - serial["median_ms"]
        ),
        "serial_budget_p95_ms": (
            stock["p95_ms"] - serial["p95_ms"]
        ),
        "async_budget_median_ms": (
            stock["median_ms"] - async_["median_ms"]
        ),
        "async_budget_p95_ms": (
            stock["p95_ms"] - async_["p95_ms"]
        ),
        "serial_to_stock_median_ratio": (
            serial["median_ms"] / stock["median_ms"]
        ),
        "serial_to_stock_p95_ratio": (
            serial["p95_ms"] / stock["p95_ms"]
        ),
        "async_to_stock_median_ratio": (
            async_["median_ms"] / stock["median_ms"]
        ),
        "async_to_stock_p95_ratio": (
            async_["p95_ms"] / stock["p95_ms"]
        ),
    }


def _case_decision(row: dict[str, Any]) -> dict[str, Any]:
    activation = _window_summary(
        row,
        field="activation_ready_ms",
    )
    route = _window_summary(
        row,
        field="route_ready_ms",
    )

    serial_survives = all(
        (
            serial["median_ms"] < stock["median_ms"]
            and serial["p95_ms"] < stock["p95_ms"]
        )
        for serial, stock in (
            (row["serial"]["route_ready_ms"], row["stock"]["route_ready_ms"]),
            (
                row["serial"]["activation_ready_ms"],
                row["stock"]["activation_ready_ms"],
            ),
        )
    )
    async_survives = all(
        (
            async_["median_ms"] < stock["median_ms"]
            and async_["p95_ms"] < stock["p95_ms"]
        )
        for async_, stock in (
            (row["async"]["route_ready_ms"], row["stock"]["route_ready_ms"]),
            (
                row["async"]["activation_ready_ms"],
                row["stock"]["activation_ready_ms"],
            ),
        )
    )
    async_overlap_retained = (
        row["async"]["route_ready_ms"]["median_ms"]
        < row["serial"]["route_ready_ms"]["median_ms"]
        and row["async"]["route_ready_ms"]["p95_ms"]
        <= row["serial"]["route_ready_ms"]["p95_ms"]
    )

    return {
        "gpu_hits": row["gpu_hits"],
        "cpu_misses": row["cpu_misses"],
        "pre_exactness": row["pre_exactness"],
        "post_exactness": row["post_exactness"],
        "activation_ready": activation,
        "route_ready": route,
        "serial_survives_stock": serial_survives,
        "async_survives_stock": async_survives,
        "async_overlap_retained": async_overlap_retained,
    }


def validate_live_moe_handoff_timing(
    h2_payload: dict[str, Any],
    h3_payload: dict[str, Any],
) -> dict[str, Any]:
    h2 = _validate_raw(h2_payload, expected_h=2)
    h3 = _validate_raw(h3_payload, expected_h=3)

    if h2["routing_weights"] != h3["routing_weights"]:
        raise LiveMoeHandoffTimingError(
            "h=2 and h=3 routing weights differ"
        )

    cases = [_case_decision(h2), _case_decision(h3)]
    async_go = all(
        row["async_survives_stock"]
        and row["async_overlap_retained"]
        for row in cases
    )
    serial_go = all(
        row["serial_survives_stock"]
        for row in cases
    )

    if async_go:
        decision = "LIVE_MOE_HANDOFF_TIMING_GO"
        chosen = "async"
    elif serial_go:
        decision = "LIVE_MOE_HANDOFF_TIMING_SERIAL_PIVOT"
        chosen = "serial"
    else:
        decision = "LIVE_MOE_HANDOFF_TIMING_NO_GO"
        chosen = "none"

    if chosen == "async":
        route_median_budgets = [
            row["route_ready"]["async_budget_median_ms"]
            for row in cases
        ]
        route_p95_budgets = [
            row["route_ready"]["async_budget_p95_ms"]
            for row in cases
        ]
        activation_median_budgets = [
            row["activation_ready"]["async_budget_median_ms"]
            for row in cases
        ]
        activation_p95_budgets = [
            row["activation_ready"]["async_budget_p95_ms"]
            for row in cases
        ]
    elif chosen == "serial":
        route_median_budgets = [
            row["route_ready"]["serial_budget_median_ms"]
            for row in cases
        ]
        route_p95_budgets = [
            row["route_ready"]["serial_budget_p95_ms"]
            for row in cases
        ]
        activation_median_budgets = [
            row["activation_ready"]["serial_budget_median_ms"]
            for row in cases
        ]
        activation_p95_budgets = [
            row["activation_ready"]["serial_budget_p95_ms"]
            for row in cases
        ]
    else:
        route_median_budgets = []
        route_p95_budgets = []
        activation_median_budgets = []
        activation_p95_budgets = []

    return {
        "schema": "tesy.live_moe_handoff_timing_summary.v1",
        "classification": "MEASURED_LIVE_MOE_HANDOFF_TIMING_DIAGNOSTIC",
        "status": "PASS",
        "decision": decision,
        "chosen_execution": chosen,
        "decode_input_token": _EXPECTED_TOKEN,
        "selected_experts": _EXPECTED_EXPERTS,
        "routing_weights": h2["routing_weights"],
        "cases": cases,
        "reinjection_budget": {
            "route_median_min_ms": (
                min(route_median_budgets)
                if route_median_budgets
                else None
            ),
            "route_p95_min_ms": (
                min(route_p95_budgets)
                if route_p95_budgets
                else None
            ),
            "activation_median_min_ms": (
                min(activation_median_budgets)
                if activation_median_budgets
                else None
            ),
            "activation_p95_min_ms": (
                min(activation_p95_budgets)
                if activation_p95_budgets
                else None
            ),
        },
        "claim_boundary": (
            "Resident-expert live-handoff timing for one repeated stock "
            "layer-0 route. The chosen execution must preserve positive "
            "median and p95 headroom against the within-process stock "
            "comparator for h=2 and h=3. The measured minimum headroom is "
            "a diagnostic ceiling for a future "
            "output-reinjection/continuation gate under the same "
            "callback-instrumented comparator. It is not a production "
            "stock-latency bound; committed-token same-work validation "
            "against unmodified stock remains required. No full-model, "
            "cache-miss, prefetch or physical-traffic conclusion follows."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--h2", required=True, type=Path)
    parser.add_argument("--h3", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to replace {args.output}")

    h2 = _load_json(args.h2)
    h3 = _load_json(args.h3)
    if not isinstance(h2, dict) or not isinstance(h3, dict):
        raise SystemExit("timing inputs must be JSON objects")

    result = validate_live_moe_handoff_timing(h2, h3)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
