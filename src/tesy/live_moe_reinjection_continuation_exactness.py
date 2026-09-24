"""Validação independente do gate live de reinjection e continuation."""

from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path


class ReinjectionValidationError(ValueError):
    pass


RAW_SCHEMA = "tesy.live_moe_reinjection_continuation_exactness_raw.v1"
SUMMARY_SCHEMA = "tesy.live_moe_reinjection_continuation_exactness_summary.v1"
DECISION = "LIVE_MOE_REINJECTION_CONTINUATION_EXACTNESS_GO"
FORBIDDEN = ("median_ms", "p95_ms", "samples_ms", "speedup", "tok_s", "tpot", "ttft")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReinjectionValidationError(message)


def _reject_performance(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _require(not any(term in key.lower() for term in FORBIDDEN),
                     f"performance field forbidden: {key}")
            _reject_performance(child)
    elif isinstance(value, list):
        for child in value:
            _reject_performance(child)


def _read_logits(root: Path, name: str, checkpoint: str, count: int) -> tuple[bytes, list[float]]:
    path = root / f"{name}-{checkpoint}.f32"
    payload = path.read_bytes()
    _require(len(payload) == count * 4, f"{path.name}: logits byte count mismatch")
    values = [entry[0] for entry in struct.iter_unpack("<f", payload)]
    _require(all(math.isfinite(value) for value in values),
             f"{path.name}: non-finite logits")
    return payload, values


def _parity(reference: list[float], candidate: list[float],
            reference_bytes: bytes, candidate_bytes: bytes) -> dict[str, object]:
    max_abs = max(abs(a - b) for a, b in zip(reference, candidate, strict=True))
    max_abs_ref = max(abs(a) for a in reference)
    relative_max = max_abs / max(1.0, max_abs_ref)
    dot = math.fsum(a * b for a, b in zip(reference, candidate, strict=True))
    norm_ref = math.fsum(a * a for a in reference)
    norm_candidate = math.fsum(b * b for b in candidate)
    cosine = dot / max(1e-30, math.sqrt(norm_ref * norm_candidate))
    passed = all(math.isfinite(x) for x in (max_abs, max_abs_ref, relative_max, cosine))
    passed = passed and relative_max <= 0.005 and cosine >= 0.9999
    return {
        "element_count": len(reference),
        "max_abs": max_abs,
        "max_abs_ref": max_abs_ref,
        "relative_max": relative_max,
        "cosine": cosine,
        "bitwise_equal": reference_bytes == candidate_bytes,
        "status": "PASS" if passed else "FAIL",
    }


def validate(raw_path: Path) -> dict[str, object]:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    _reject_performance(raw)
    _require(raw.get("schema") == RAW_SCHEMA, "raw schema mismatch")
    _require("decision" not in raw, "native raw must not declare a decision")
    _require(raw.get("layer") == 0 and raw.get("ngl") == 0,
             "expected stock layer-0 CPU context")
    _require(raw.get("first_token") == 2167 and raw.get("second_token") == 1309,
             "frozen first/second tokens mismatch")
    count = raw.get("logits_count")
    _require(type(count) is int and count > 100000, "full vocabulary logits required")
    third = raw.get("stock_third_token")
    _require(type(third) is int and 0 <= third < count, "invalid stock third token")
    arms = raw.get("arms")
    _require(type(arms) is dict and set(arms) == {"stock", "control", "h2", "h3"},
             "four frozen arms required")
    stock = arms["stock"]
    _require(stock.get("gpu_hits") == 0 and stock.get("injection_count") == 0,
             "uninterrupted stock baseline altered")
    root = raw_path.parent
    logits: dict[tuple[str, str], tuple[bytes, list[float]]] = {}
    result_arms: dict[str, dict[str, object]] = {}
    for name in ("stock", "control", "h2", "h3"):
        arm = arms[name]
        _require(type(arm) is dict, f"{name}: invalid arm")
        _require(arm.get("gpu_hits") == {"stock": 0, "control": 0, "h2": 2, "h3": 3}[name],
                 f"{name}: gpu_hits mismatch")
        _require(arm.get("first_token") == 2167 and arm.get("second_token") == 1309
                 and arm.get("third_token") == third, f"{name}: token mismatch")
        _require(arm.get("committed_decode_return_code") == 0
                 and arm.get("continuation_decode_return_code") == 0,
                 f"{name}: decode failure")
        for checkpoint in ("a", "b"):
            _require(arm.get(f"logits_{checkpoint}_file") == f"{name}-{checkpoint}.f32",
                     f"{name}: logits path mismatch")
            logits[(name, checkpoint)] = _read_logits(root, name, checkpoint, count)
        if name == "stock":
            continue
        _require(arm.get("injection_count") == 1
                 and arm.get("stock_capture_rollback") is True
                 and arm.get("handoff_capture_rollback") is True
                 and arm.get("injected_bytes_verified") is True,
                 f"{name}: injection/capture contract failed")
        _require(arm.get("selected_experts") == [1, 13, 17, 21],
                 f"{name}: route mismatch")
        _require(arm.get("routing_weights") == arms["control"].get("routing_weights"),
                 f"{name}: routing weights mismatch")
        for key in ("activation_pair_parity", "ffn_parity", "pre_overwrite_parity"):
            value = arm.get(key)
            _require(type(value) is dict and value.get("status") == "PASS",
                     f"{name}: {key} failed")
            _require(all(type(value.get(field)) in (int, float)
                         and math.isfinite(value[field])
                         for field in ("max_abs", "max_abs_ref", "relative_max", "cosine")),
                     f"{name}: {key} non-finite")
            _require(value["relative_max"] <= 0.005 and value["cosine"] >= 0.9999,
                     f"{name}: {key} threshold failure")
        if name == "control":
            _require(arm.get("ffn_bitwise") is True,
                     "stock-output injection must use stock bytes")
        checkpoints: dict[str, dict[str, object]] = {}
        for checkpoint in ("a", "b"):
            ref_bytes, ref_values = logits[("stock", checkpoint)]
            candidate_bytes, candidate_values = logits[(name, checkpoint)]
            parity = _parity(ref_values, candidate_values, ref_bytes, candidate_bytes)
            _require(parity["status"] == "PASS", f"{name}: checkpoint {checkpoint} parity failed")
            checkpoints[checkpoint] = parity
        result_arms[name] = {
            "gpu_hits": arm["gpu_hits"],
            "first_token": arm["first_token"],
            "second_token": arm["second_token"],
            "third_token": arm["third_token"],
            "ffn_parity": arm["ffn_parity"],
            "ffn_bitwise": arm["ffn_bitwise"],
            "activation_pair_bitwise": arm["activation_pair_bitwise"],
            "pre_overwrite_parity": arm["pre_overwrite_parity"],
            "pre_overwrite_bitwise": arm["pre_overwrite_bitwise"],
            "injection_count": arm["injection_count"],
            "checkpoint_a": checkpoints["a"],
            "checkpoint_b": checkpoints["b"],
        }
    return {
        "schema": SUMMARY_SCHEMA,
        "classification": "MEASURED_LIVE_MOE_REINJECTION_CONTINUATION_EXACTNESS",
        "status": "PASS",
        "decision": DECISION,
        "stock_tokens": [2167, 1309, third],
        "logits_count": count,
        "arms": result_arms,
        "claim_boundary": raw["claim_boundary"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = validate(args.input)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(summary["decision"])


if __name__ == "__main__":
    main()
