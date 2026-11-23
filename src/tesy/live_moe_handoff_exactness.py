from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


class LiveMoeHandoffExactnessError(ValueError):
    pass


_EXPECTED_TOKEN = 2167
_EXPECTED_EXPERTS = [1, 13, 17, 21]
_EXPECTED_THRESHOLDS = {
    "relative_max_max": 0.005,
    "cosine_min": 0.9999,
}
_FORBIDDEN_TIMING_KEYS = {
    "median_ms",
    "p95_ms",
    "min_ms",
    "max_ms",
    "mean_ms",
    "samples_ms",
    "speedup",
}


def _finite_float(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LiveMoeHandoffExactnessError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise LiveMoeHandoffExactnessError(f"{label} must be finite")
    return number


def _parity(payload: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LiveMoeHandoffExactnessError(f"{label} must be an object")
    if payload.get("status") != "PASS":
        raise LiveMoeHandoffExactnessError(f"{label} did not PASS")

    relative = _finite_float(
        payload.get("relative_max"),
        label=f"{label}.relative_max",
    )
    cosine = _finite_float(
        payload.get("cosine"),
        label=f"{label}.cosine",
    )
    _finite_float(payload.get("max_abs"), label=f"{label}.max_abs")
    _finite_float(
        payload.get("max_abs_ref"),
        label=f"{label}.max_abs_ref",
    )

    if relative > _EXPECTED_THRESHOLDS["relative_max_max"]:
        raise LiveMoeHandoffExactnessError(
            f"{label} relative_max threshold violated"
        )
    if cosine < _EXPECTED_THRESHOLDS["cosine_min"]:
        raise LiveMoeHandoffExactnessError(
            f"{label} cosine threshold violated"
        )
    return payload


def _reject_timing_fields(value: Any, *, path: str = "root") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _FORBIDDEN_TIMING_KEYS:
                raise LiveMoeHandoffExactnessError(
                    f"timing field forbidden in exactness gate: {path}.{key}"
                )
            _reject_timing_fields(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_timing_fields(child, path=f"{path}[{index}]")


def validate_live_moe_handoff_exactness(
    payload: dict[str, Any],
) -> dict[str, Any]:
    _reject_timing_fields(payload)

    if payload.get("schema") != "tesy.live_moe_handoff_exactness.v1":
        raise LiveMoeHandoffExactnessError("schema mismatch")
    if (
        payload.get("classification")
        != "MEASURED_LIVE_MOE_HANDOFF_EXACTNESS"
    ):
        raise LiveMoeHandoffExactnessError("classification mismatch")

    expected = {
        "layer": 0,
        "ngl": 0,
        "decode_input_token": _EXPECTED_TOKEN,
        "stock_decode_return_code": 0,
        "handoff_decode_return_code": 0,
        "stock_rollback": True,
        "handoff_rollback": True,
        "activation_tensor": "attn_post_norm-0",
        "topk_tensor": "ffn_moe_topk-0",
        "routing_weight_tensor": "ffn_moe_weights_softmax-0",
        "stock_output_tensor": "ffn_moe_out-0",
        "selected_experts": _EXPECTED_EXPERTS,
        "parity_thresholds": _EXPECTED_THRESHOLDS,
        "decision": "LIVE_MOE_HANDOFF_EXACTNESS_GO",
    }
    for field, expected_value in expected.items():
        if payload.get(field) != expected_value:
            raise LiveMoeHandoffExactnessError(
                f"{field} mismatch: {payload.get(field)!r}"
            )

    bitwise = payload.get("activation_bitwise_equal")
    if not isinstance(bitwise, bool):
        raise LiveMoeHandoffExactnessError(
            "activation_bitwise_equal must be boolean"
        )

    activation_parity = _parity(
        payload.get("activation_parity"),
        label="activation_parity",
    )

    weights = payload.get("routing_weights")
    if not isinstance(weights, list) or len(weights) != 4:
        raise LiveMoeHandoffExactnessError(
            "routing_weights must contain four values"
        )
    parsed_weights: list[float] = []
    for value in weights:
        number = _finite_float(value, label="routing_weights")
        if number < 0.0:
            raise LiveMoeHandoffExactnessError(
                "routing weights must be non-negative"
            )
        parsed_weights.append(number)

    cases = payload.get("cases")
    if not isinstance(cases, list) or len(cases) != 2:
        raise LiveMoeHandoffExactnessError(
            "cases must contain exactly h=2 and h=3"
        )

    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for raw in cases:
        if not isinstance(raw, dict):
            raise LiveMoeHandoffExactnessError("case must be an object")
        h = raw.get("gpu_hits")
        if h not in {2, 3} or h in seen:
            raise LiveMoeHandoffExactnessError(
                "cases must contain unique gpu_hits 2 and 3"
            )
        seen.add(h)
        if raw.get("cpu_misses") != 4 - h:
            raise LiveMoeHandoffExactnessError(
                f"h={h} cpu_misses mismatch"
            )

        rows.append(
            {
                "gpu_hits": h,
                "cpu_misses": raw["cpu_misses"],
                "serial_vs_stock": _parity(
                    raw.get("serial_vs_stock"),
                    label=f"h{h}.serial_vs_stock",
                ),
                "async_vs_stock": _parity(
                    raw.get("async_vs_stock"),
                    label=f"h{h}.async_vs_stock",
                ),
                "async_vs_serial": _parity(
                    raw.get("async_vs_serial"),
                    label=f"h{h}.async_vs_serial",
                ),
            }
        )

    if seen != {2, 3}:
        raise LiveMoeHandoffExactnessError("missing h=2 or h=3 case")

    return {
        "schema": "tesy.live_moe_handoff_exactness_summary.v1",
        "classification": "MEASURED_LIVE_MOE_HANDOFF_EXACTNESS_DIAGNOSTIC",
        "status": "PASS",
        "decision": "LIVE_MOE_HANDOFF_EXACTNESS_GO",
        "decode_input_token": _EXPECTED_TOKEN,
        "selected_experts": _EXPECTED_EXPERTS,
        "routing_weights": parsed_weights,
        "activation_bitwise_equal": bitwise,
        "activation_parity": activation_parity,
        "parity_thresholds": _EXPECTED_THRESHOLDS,
        "cases": sorted(rows, key=lambda row: row["gpu_hits"]),
        "claim_boundary": (
            "One in-process stock-reference arm and one in-process live "
            "handoff arm reproduce the same layer-0 token/route after "
            "explicit KV rollback. Tesy h=2/h=3 serial and async compact "
            "FFNs consume the activation captured from the handoff arm and "
            "match the stock-reference ffn_moe_out within frozen numerical "
            "thresholds. This is exactness-only evidence: no timing, output "
            "reinjection, committed-token continuation, cache/prefetch or "
            "physical-traffic conclusion follows."
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
        raise SystemExit("live handoff input must be a JSON object")

    result = validate_live_moe_handoff_exactness(payload)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
