from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


class RoutedLayerExactnessError(ValueError):
    pass


_EXPECTED_PARITY = {
    "relative_max_max": 0.005,
    "cosine_min": 0.9999,
}
_EXPECTED_H = {2, 3}
_ALLOWED_WEIGHT_TENSORS = {
    "ffn_moe_weights_softmax-0",
    "ffn_moe_weights_scaled-0",
}


def _tokens(payload: Any, *, label: str) -> list[int]:
    if not isinstance(payload, dict):
        raise RoutedLayerExactnessError(f"{label} must be an object")
    if payload.get("schema") != "tesy.routed_layer_capture_tokens.v1":
        raise RoutedLayerExactnessError(f"{label} schema mismatch")
    values = payload.get("tokens")
    if (
        not isinstance(values, list)
        or len(values) != 2
        or any(isinstance(v, bool) or not isinstance(v, int) for v in values)
    ):
        raise RoutedLayerExactnessError(
            f"{label}.tokens must contain exactly two integers"
        )
    return values


def _finite_float(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RoutedLayerExactnessError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise RoutedLayerExactnessError(f"{label} must be finite")
    return number


def _parity(payload: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RoutedLayerExactnessError(f"{label} must be an object")
    if payload.get("status") != "PASS":
        raise RoutedLayerExactnessError(f"{label} did not PASS")
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
    if relative > _EXPECTED_PARITY["relative_max_max"]:
        raise RoutedLayerExactnessError(
            f"{label} relative_max threshold violated"
        )
    if cosine < _EXPECTED_PARITY["cosine_min"]:
        raise RoutedLayerExactnessError(
            f"{label} cosine threshold violated"
        )
    return payload


def validate_capture_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != "tesy.routed_layer_capture.v1":
        raise RoutedLayerExactnessError("capture metadata schema mismatch")
    if (
        payload.get("classification")
        != "MEASURED_STOCK_ROUTED_LAYER_CAPTURE"
    ):
        raise RoutedLayerExactnessError(
            "capture metadata classification mismatch"
        )
    expected = {
        "layer": 0,
        "phase": "decode",
        "n_embd": 2880,
        "n_expert_used": 4,
        "activation_tensor": "attn_post_norm-0",
        "topk_tensor": "ffn_moe_topk-0",
        "stock_output_tensor": "ffn_moe_out-0",
        "activation_file": "activation.f32",
        "stock_output_file": "stock-output.f32",
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise RoutedLayerExactnessError(
                f"capture {field} mismatch: {payload.get(field)!r}"
            )

    weight_tensor = payload.get("routing_weight_tensor")
    if weight_tensor not in _ALLOWED_WEIGHT_TENSORS:
        raise RoutedLayerExactnessError(
            f"unexpected routing weight tensor: {weight_tensor!r}"
        )

    experts = payload.get("selected_experts")
    if (
        not isinstance(experts, list)
        or len(experts) != 4
        or any(
            isinstance(v, bool)
            or not isinstance(v, int)
            or v < 0
            or v >= 32
            for v in experts
        )
        or len(set(experts)) != 4
    ):
        raise RoutedLayerExactnessError(
            "capture selected_experts must be four unique IDs in 0..31"
        )

    weights = payload.get("routing_weights")
    if not isinstance(weights, list) or len(weights) != 4:
        raise RoutedLayerExactnessError(
            "capture routing_weights must contain four values"
        )
    parsed_weights = [
        _finite_float(value, label="capture.routing_weights")
        for value in weights
    ]
    if any(value < 0.0 for value in parsed_weights):
        raise RoutedLayerExactnessError(
            "capture routing weights must be non-negative"
        )

    for field in ("decode_input_token", "decode_output_token"):
        value = payload.get(field)
        if isinstance(value, bool) or not isinstance(value, int):
            raise RoutedLayerExactnessError(
                f"capture {field} must be an integer"
            )

    return {
        "selected_experts": experts,
        "routing_weights": parsed_weights,
        "routing_weight_tensor": weight_tensor,
        "decode_input_token": payload["decode_input_token"],
        "decode_output_token": payload["decode_output_token"],
    }


def validate_replay(
    payload: dict[str, Any],
    *,
    expected_h: int,
    experts: list[int],
    weights: list[float],
) -> dict[str, Any]:
    if payload.get("schema") != "tesy.routed_layer_exactness_raw.v1":
        raise RoutedLayerExactnessError(
            f"h{expected_h} replay schema mismatch"
        )
    if (
        payload.get("classification")
        != "MEASURED_ROUTED_LAYER_REPLAY_EXACTNESS"
    ):
        raise RoutedLayerExactnessError(
            f"h{expected_h} replay classification mismatch"
        )
    if payload.get("layer") != 0:
        raise RoutedLayerExactnessError(
            f"h{expected_h} replay layer mismatch"
        )
    if payload.get("gpu_hits") != expected_h:
        raise RoutedLayerExactnessError(
            f"h{expected_h} replay gpu_hits mismatch"
        )
    if payload.get("cpu_misses") != 4 - expected_h:
        raise RoutedLayerExactnessError(
            f"h{expected_h} replay cpu_misses mismatch"
        )
    if (
        payload.get("controlled_partition")
        != "TOPK_SLOT_PREFIX_GPU_REMAINDER_CPU"
    ):
        raise RoutedLayerExactnessError(
            f"h{expected_h} controlled partition mismatch"
        )
    if payload.get("selected_experts") != experts:
        raise RoutedLayerExactnessError(
            f"h{expected_h} selected experts differ from capture"
        )
    observed_weights = payload.get("routing_weights")
    if not isinstance(observed_weights, list) or len(observed_weights) != 4:
        raise RoutedLayerExactnessError(
            f"h{expected_h} routing weights malformed"
        )
    observed = [
        _finite_float(value, label=f"h{expected_h}.routing_weights")
        for value in observed_weights
    ]
    if observed != weights:
        raise RoutedLayerExactnessError(
            f"h{expected_h} routing weights differ from capture"
        )

    thresholds = payload.get("parity_thresholds")
    if thresholds != _EXPECTED_PARITY:
        raise RoutedLayerExactnessError(
            f"h{expected_h} parity threshold contract mismatch"
        )

    return {
        "gpu_hits": expected_h,
        "serial_vs_stock": _parity(
            payload.get("serial_vs_stock"),
            label=f"h{expected_h}.serial_vs_stock",
        ),
        "async_vs_stock": _parity(
            payload.get("async_vs_stock"),
            label=f"h{expected_h}.async_vs_stock",
        ),
        "async_vs_serial": _parity(
            payload.get("async_vs_serial"),
            label=f"h{expected_h}.async_vs_serial",
        ),
    }


def validate_routed_layer_exactness(
    *,
    capture_metadata: dict[str, Any],
    off_tokens: dict[str, Any],
    on_tokens: dict[str, Any],
    replay_h2: dict[str, Any],
    replay_h3: dict[str, Any],
) -> dict[str, Any]:
    off = _tokens(off_tokens, label="off")
    on = _tokens(on_tokens, label="on")
    if off != on:
        raise RoutedLayerExactnessError(
            "capture OFF/ON greedy token IDs differ"
        )

    capture = validate_capture_metadata(capture_metadata)
    if capture["decode_input_token"] != on[0]:
        raise RoutedLayerExactnessError(
            "capture decode input token differs from generated token[0]"
        )
    if capture["decode_output_token"] != on[1]:
        raise RoutedLayerExactnessError(
            "capture decode output token differs from generated token[1]"
        )

    rows = []
    for h, payload in ((2, replay_h2), (3, replay_h3)):
        rows.append(
            validate_replay(
                payload,
                expected_h=h,
                experts=capture["selected_experts"],
                weights=capture["routing_weights"],
            )
        )

    if {row["gpu_hits"] for row in rows} != _EXPECTED_H:
        raise RoutedLayerExactnessError(
            "routed replay must contain h=2 and h=3"
        )

    return {
        "schema": "tesy.routed_layer_exactness_summary.v1",
        "classification": "MEASURED_ROUTED_LAYER_EXACTNESS_DIAGNOSTIC",
        "status": "PASS",
        "decision": "ROUTED_LAYER_EXACTNESS_GO",
        "token_ids": on,
        "selected_experts": capture["selected_experts"],
        "routing_weights": capture["routing_weights"],
        "routing_weight_tensor": capture["routing_weight_tensor"],
        "parity_thresholds": _EXPECTED_PARITY,
        "cases": rows,
        "claim_boundary": (
            "One stock llama.cpp layer-0 decode event supplies the exact "
            "activation, router top-k, final routing weights and stock MoE "
            "output. Serial and async compact replays for controlled h=2/h=3 "
            "partitions reproduce that stock output within the frozen "
            "numerical-parity thresholds. This is correctness-only evidence; "
            "it does not measure routed-layer latency, full-model speed, "
            "residency policy, cache/prefetch behavior or physical traffic."
        ),
    }


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RoutedLayerExactnessError(f"{path} must contain an object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture-metadata", required=True, type=Path)
    parser.add_argument("--off-tokens", required=True, type=Path)
    parser.add_argument("--on-tokens", required=True, type=Path)
    parser.add_argument("--replay-h2", required=True, type=Path)
    parser.add_argument("--replay-h3", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to replace {args.output}")

    result = validate_routed_layer_exactness(
        capture_metadata=_load(args.capture_metadata),
        off_tokens=_load(args.off_tokens),
        on_tokens=_load(args.on_tokens),
        replay_h2=_load(args.replay_h2),
        replay_h3=_load(args.replay_h3),
    )

    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
