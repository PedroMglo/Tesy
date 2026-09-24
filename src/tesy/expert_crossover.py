from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


class ExpertCrossoverError(ValueError):
    pass


_EXPECTED_K = [1, 4]
_BYTES_PER_EXPERT = 13_253_760
_ACTIVATION_BYTES = 2880 * 4


def _finite_number(value: Any, *, label: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ExpertCrossoverError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ExpertCrossoverError(f"{label} must be finite")
    if positive and number <= 0:
        raise ExpertCrossoverError(f"{label} must be positive")
    return number


def _validate_stats(payload: Any, *, label: str, expected_samples: int) -> None:
    if not isinstance(payload, dict):
        raise ExpertCrossoverError(f"{label} must be an object")
    samples = payload.get("samples_ms")
    if not isinstance(samples, list) or len(samples) != expected_samples:
        raise ExpertCrossoverError(
            f"{label}.samples_ms must contain {expected_samples} samples"
        )
    values = [
        _finite_number(value, label=f"{label}.samples_ms", positive=True)
        for value in samples
    ]
    for field in ("median_ms", "p95_ms", "min_ms", "max_ms", "mean_ms"):
        _finite_number(payload.get(field), label=f"{label}.{field}", positive=True)
    if payload["min_ms"] > payload["median_ms"]:
        raise ExpertCrossoverError(f"{label} min exceeds median")
    if payload["median_ms"] > payload["max_ms"]:
        raise ExpertCrossoverError(f"{label} median exceeds max")
    if payload["p95_ms"] > payload["max_ms"]:
        raise ExpertCrossoverError(f"{label} p95 exceeds max")
    if min(values) != payload["min_ms"] or max(values) != payload["max_ms"]:
        raise ExpertCrossoverError(f"{label} min/max do not match raw samples")
    ordered = sorted(values)
    expected_median = ordered[len(ordered) // 2]
    expected_p95 = ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]
    expected_mean = sum(ordered) / len(ordered)
    for field, expected in (
        ("median_ms", expected_median),
        ("p95_ms", expected_p95),
        ("mean_ms", expected_mean),
    ):
        observed = float(payload[field])
        if not math.isclose(observed, expected, rel_tol=1e-9, abs_tol=1e-9):
            raise ExpertCrossoverError(
                f"{label} {field} does not match raw samples"
            )


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-9)


def validate_expert_crossover(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != "tesy.expert_crossover_raw.v1":
        raise ExpertCrossoverError("unsupported crossover schema")
    if payload.get("classification") != "MEASURED_EXPERT_CROSSOVER_MICROBENCHMARK":
        raise ExpertCrossoverError("unexpected crossover classification")

    expected_scalars = {
        "layer": 0,
        "threads": 12,
        "n_embd": 2880,
        "expert_count_model": 32,
        "encoded_bytes_per_expert": _BYTES_PER_EXPERT,
        "weight_type": "mxfp4",
        "bias_type": "f32",
        "weight_shape": [2880, 2880, 32],
        "bias_shape": [2880, 32],
    }
    for field, expected in expected_scalars.items():
        if payload.get(field) != expected:
            raise ExpertCrossoverError(
                f"{field} mismatch: {payload.get(field)!r} != {expected!r}"
            )

    samples = payload.get("samples")
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 5:
        raise ExpertCrossoverError("samples must be an integer >= 5")

    results = payload.get("results")
    if not isinstance(results, list) or [row.get("k") for row in results] != _EXPECTED_K:
        raise ExpertCrossoverError("results must contain k=1 then k=4")

    rows: list[dict[str, Any]] = []
    for row in results:
        k = row["k"]
        if row.get("source_expert_ids") != list(range(k)):
            raise ExpertCrossoverError(f"unexpected source expert IDs for k={k}")
        if row.get("requested_weight_bytes") != _BYTES_PER_EXPERT * k:
            raise ExpertCrossoverError(f"requested weight bytes mismatch for k={k}")
        if row.get("activation_input_bytes") != _ACTIVATION_BYTES:
            raise ExpertCrossoverError(f"input activation bytes mismatch for k={k}")
        if row.get("activation_output_bytes") != _ACTIVATION_BYTES:
            raise ExpertCrossoverError(f"output activation bytes mismatch for k={k}")

        buffer_type = row.get("cpu_weight_buffer_type")
        if buffer_type != "CPU":
            raise ExpertCrossoverError(
                f"expected CPU default buffer for k={k}, got {buffer_type!r}"
            )
        weight_buffer_bytes = row.get("cpu_weight_buffer_bytes")
        bias_buffer_bytes = row.get("cpu_bias_buffer_bytes")
        for field, value in {
            "cpu_weight_buffer_bytes": weight_buffer_bytes,
            "cpu_bias_buffer_bytes": bias_buffer_bytes,
        }.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ExpertCrossoverError(f"invalid {field} for k={k}")
        if weight_buffer_bytes + bias_buffer_bytes < row["requested_weight_bytes"]:
            raise ExpertCrossoverError(
                f"CPU expert buffers smaller than encoded payload for k={k}"
            )

        for name in (
            "cpu_compute",
            "gpu_compute",
            "activation_d2h",
            "activation_h2d",
            "weight_h2d_pageable",
        ):
            _validate_stats(row.get(name), label=f"k{k}.{name}", expected_samples=samples)

        pinned = row.get("pinned_available")
        if not isinstance(pinned, bool):
            raise ExpertCrossoverError(f"pinned_available must be bool for k={k}")
        if pinned:
            _validate_stats(
                row.get("weight_h2d_pinned"),
                label=f"k{k}.weight_h2d_pinned",
                expected_samples=samples,
            )
        elif row.get("weight_h2d_pinned") is not None:
            raise ExpertCrossoverError(
                f"pinned timing must be null when unavailable for k={k}"
            )

        parity = row.get("parity")
        if not isinstance(parity, dict) or parity.get("status") != "PASS":
            raise ExpertCrossoverError(f"CPU/GPU parity did not PASS for k={k}")
        for name in ("max_abs", "max_abs_ref", "relative_max", "cosine"):
            _finite_number(parity.get(name), label=f"k{k}.parity.{name}")
        if parity["relative_max"] > 0.005 or parity["cosine"] < 0.9999:
            raise ExpertCrossoverError(f"parity threshold violated for k={k}")

        derived = row.get("derived")
        if not isinstance(derived, dict):
            raise ExpertCrossoverError(f"missing derived paths for k={k}")
        cpu_expected = (
            row["activation_d2h"]["median_ms"]
            + row["cpu_compute"]["median_ms"]
            + row["activation_h2d"]["median_ms"]
        )
        pageable_expected = (
            row["weight_h2d_pageable"]["median_ms"]
            + row["gpu_compute"]["median_ms"]
        )
        resident_expected = row["gpu_compute"]["median_ms"]
        for name, expected in (
            ("cpu_path_median_ms", cpu_expected),
            ("cold_gpu_pageable_median_ms", pageable_expected),
            ("resident_gpu_median_ms", resident_expected),
        ):
            observed = _finite_number(
                derived.get(name), label=f"k{k}.derived.{name}", positive=True
            )
            if not _close(observed, expected):
                raise ExpertCrossoverError(
                    f"derived path mismatch for k={k} {name}"
                )

        if pinned:
            pinned_expected = (
                row["weight_h2d_pinned"]["median_ms"]
                + row["gpu_compute"]["median_ms"]
            )
            observed = _finite_number(
                derived.get("cold_gpu_pinned_median_ms"),
                label=f"k{k}.derived.cold_gpu_pinned_median_ms",
                positive=True,
            )
            if not _close(observed, pinned_expected):
                raise ExpertCrossoverError(
                    f"derived pinned path mismatch for k={k}"
                )
        elif derived.get("cold_gpu_pinned_median_ms") is not None:
            raise ExpertCrossoverError(
                f"derived pinned path must be null for k={k}"
            )

        rows.append(
            {
                "k": k,
                "requested_weight_bytes": row["requested_weight_bytes"],
                "cpu_weight_buffer_type": buffer_type,
                "cpu_weight_buffer_bytes": row["cpu_weight_buffer_bytes"],
                "cpu_bias_buffer_bytes": row["cpu_bias_buffer_bytes"],
                "parity": parity,
                "median_ms": {
                    "cpu_compute": row["cpu_compute"]["median_ms"],
                    "gpu_compute": row["gpu_compute"]["median_ms"],
                    "activation_d2h": row["activation_d2h"]["median_ms"],
                    "activation_h2d": row["activation_h2d"]["median_ms"],
                    "weight_h2d_pageable": row["weight_h2d_pageable"]["median_ms"],
                    "weight_h2d_pinned": (
                        row["weight_h2d_pinned"]["median_ms"] if pinned else None
                    ),
                    "cpu_path": derived["cpu_path_median_ms"],
                    "cold_gpu_pageable": derived["cold_gpu_pageable_median_ms"],
                    "cold_gpu_pinned": derived["cold_gpu_pinned_median_ms"],
                    "resident_gpu": derived["resident_gpu_median_ms"],
                },
            }
        )

    return {
        "schema": "tesy.expert_crossover_summary.v1",
        "classification": "MEASURED_EXPERT_CROSSOVER_DIAGNOSTIC",
        "status": "PASS",
        "cpu_device": payload.get("cpu_device"),
        "gpu_device": payload.get("gpu_device"),
        "samples": samples,
        "results": rows,
        "claim_boundary": (
            "Summary of the admitted microbenchmark medians. Requested weight-copy "
            "and activation-copy bytes/times are software-requested tensor movement, "
            "not physical PCIe traffic. CPU-path and cold-GPU path medians are sums "
            "of separately measured components and do not establish overlapped "
            "pipeline latency."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to replace {args.output}")

    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read crossover JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("crossover JSON must be an object")

    summary = validate_expert_crossover(payload)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print("PASS_EXPERT_CROSSOVER_VALIDATION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
