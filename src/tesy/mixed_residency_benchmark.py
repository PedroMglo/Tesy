from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


class MixedResidencyBenchmarkError(ValueError):
    pass


_EXPECTED_H = [0, 1, 2, 3, 4]
_EXPECTED_EXPERT_IDS = [0, 1, 2, 3]
_EXPECTED_MIX = [0.25, 0.25, 0.25, 0.25]


def _finite(value: Any, *, label: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MixedResidencyBenchmarkError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise MixedResidencyBenchmarkError(f"{label} must be finite")
    if positive and number <= 0:
        raise MixedResidencyBenchmarkError(f"{label} must be positive")
    return number


def _validate_stats(payload: Any, *, label: str, expected_samples: int) -> None:
    if not isinstance(payload, dict):
        raise MixedResidencyBenchmarkError(f"{label} must be an object")
    samples = payload.get("samples_ms")
    if not isinstance(samples, list) or len(samples) != expected_samples:
        raise MixedResidencyBenchmarkError(
            f"{label}.samples_ms must contain {expected_samples} samples"
        )
    values = [
        _finite(item, label=f"{label}.samples_ms", positive=True)
        for item in samples
    ]
    for field in ("median_ms", "p95_ms", "min_ms", "max_ms", "mean_ms"):
        _finite(payload.get(field), label=f"{label}.{field}", positive=True)
    if payload["min_ms"] != min(values) or payload["max_ms"] != max(values):
        raise MixedResidencyBenchmarkError(
            f"{label} min/max do not match raw samples"
        )
    if not (
        payload["min_ms"] <= payload["median_ms"] <= payload["max_ms"]
    ):
        raise MixedResidencyBenchmarkError(
            f"{label} median outside min/max"
        )
    if payload["p95_ms"] > payload["max_ms"]:
        raise MixedResidencyBenchmarkError(
            f"{label} p95 exceeds max"
        )
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
            raise MixedResidencyBenchmarkError(
                f"{label} {field} does not match raw samples"
            )


def validate_mixed_residency_raw(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != "tesy.mixed_residency_stage_b_raw.v1":
        raise MixedResidencyBenchmarkError("unsupported mixed-residency schema")
    if (
        payload.get("classification")
        != "MEASURED_MIXED_RESIDENCY_FFN_DIAGNOSTIC"
    ):
        raise MixedResidencyBenchmarkError(
            "unexpected mixed-residency classification"
        )

    expected = {
        "layer": 0,
        "threads": 12,
        "n_embd": 2880,
        "top_k": 4,
        "expert_count_model": 32,
        "encoded_bytes_per_expert": 13_253_760,
        "weight_type": "mxfp4",
        "bias_type": "f32",
        "weight_shape": [2880, 2880, 32],
        "bias_shape": [2880, 32],
        "expert_ids": _EXPECTED_EXPERT_IDS,
        "mix_weights": _EXPECTED_MIX,
        "measurement_order": [0, 4, 1, 3, 2],
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise MixedResidencyBenchmarkError(
                f"{field} mismatch: {payload.get(field)!r} != {value!r}"
            )

    cpu_weight_buffer_type = payload.get("cpu_weight_buffer_type")
    cpu_bias_buffer_type = payload.get("cpu_bias_buffer_type")
    if (
        not isinstance(cpu_weight_buffer_type, str)
        or not cpu_weight_buffer_type
        or not isinstance(cpu_bias_buffer_type, str)
        or not cpu_bias_buffer_type
    ):
        raise MixedResidencyBenchmarkError(
            "CPU weight/bias buffer types must be non-empty strings"
        )

    samples = payload.get("samples")
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 5:
        raise MixedResidencyBenchmarkError("samples must be an integer >= 5")

    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise MixedResidencyBenchmarkError("cases must be a list")
    if [row.get("gpu_hits") for row in cases] != _EXPECTED_H:
        raise MixedResidencyBenchmarkError("cases must contain h=0..4 in order")

    result_rows: list[dict[str, Any]] = []
    for row in cases:
        h = row["gpu_hits"]
        if row.get("cpu_misses") != 4 - h:
            raise MixedResidencyBenchmarkError(
                f"cpu_misses mismatch for h={h}"
            )
        if row.get("source_expert_ids") != _EXPECTED_EXPERT_IDS:
            raise MixedResidencyBenchmarkError(
                f"expert IDs mismatch for h={h}"
            )
        if row.get("global_mix_weight") != 0.25:
            raise MixedResidencyBenchmarkError(
                f"mix weight mismatch for h={h}"
            )

        _validate_stats(
            row.get("direct_wall"),
            label=f"h{h}.direct_wall",
            expected_samples=samples,
        )

        parity = row.get("parity")
        if not isinstance(parity, dict) or parity.get("status") != "PASS":
            raise MixedResidencyBenchmarkError(
                f"numerical parity did not PASS for h={h}"
            )
        for field in ("max_abs", "max_abs_ref", "relative_max", "cosine"):
            _finite(parity.get(field), label=f"h{h}.parity.{field}")
        if parity["relative_max"] > 0.005:
            raise MixedResidencyBenchmarkError(
                f"relative parity threshold violated for h={h}"
            )
        if parity["cosine"] < 0.9999:
            raise MixedResidencyBenchmarkError(
                f"cosine parity threshold violated for h={h}"
            )

        result_rows.append(
            {
                "gpu_hits": h,
                "cpu_misses": 4 - h,
                "median_ms": row["direct_wall"]["median_ms"],
                "p95_ms": row["direct_wall"]["p95_ms"],
                "parity": parity,
            }
        )

    all_cpu = result_rows[0]["median_ms"]
    all_gpu = result_rows[-1]["median_ms"]
    if all_cpu <= 0 or all_gpu <= 0:
        raise MixedResidencyBenchmarkError("anchor medians must be positive")

    for row in result_rows:
        row["relative_to_all_cpu"] = row["median_ms"] / all_cpu
        row["speedup_vs_all_cpu"] = all_cpu / row["median_ms"]

    return {
        "schema": "tesy.mixed_residency_stage_b_summary.v1",
        "classification": "MEASURED_MIXED_RESIDENCY_FFN_DIAGNOSTIC",
        "status": "PASS",
        "samples": samples,
        "cpu_weight_buffer_type": cpu_weight_buffer_type,
        "cpu_bias_buffer_type": cpu_bias_buffer_type,
        "cases": result_rows,
        "all_cpu_median_ms": all_cpu,
        "all_gpu_median_ms": all_gpu,
        "claim_boundary": (
            "Direct serial isolated top-4 mixed CPU/GPU expert FFN timings. "
            "Weights are already resident; no expert-weight transfer, cache lookup, "
            "prefetch, routing or full-model timing is measured. Final output is "
            "materialized on GPU and numerical parity is against an all-CPU top-4 "
            "reference with deterministic experts 0..3 and uniform 0.25 weights."
        ),
    }


def weighted_trace_diagnostic(
    summary: dict[str, Any],
    histogram: dict[str, Any],
) -> dict[str, Any]:
    if summary.get("schema") != "tesy.mixed_residency_stage_b_summary.v1":
        raise MixedResidencyBenchmarkError("unsupported Stage B summary schema")
    if summary.get("status") != "PASS":
        raise MixedResidencyBenchmarkError("Stage B summary did not PASS")
    if histogram.get("schema") != "tesy.mixed_residency_hit_histogram.v1":
        raise MixedResidencyBenchmarkError("unsupported histogram schema")
    if histogram.get("classification") != "TRACE_DERIVED_RESIDENCY_OPPORTUNITY":
        raise MixedResidencyBenchmarkError("unexpected histogram classification")

    counts = histogram.get("gpu_resident_experts_per_top4_histogram")
    if not isinstance(counts, dict) or set(counts) != {"0", "1", "2", "3", "4"}:
        raise MixedResidencyBenchmarkError("invalid grouped histogram")
    groups = histogram.get("routing_groups")
    if isinstance(groups, bool) or not isinstance(groups, int) or groups <= 0:
        raise MixedResidencyBenchmarkError("invalid routing_groups")
    parsed_counts: dict[int, int] = {}
    for h in _EXPECTED_H:
        value = counts.get(str(h))
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise MixedResidencyBenchmarkError(f"invalid histogram count h={h}")
        parsed_counts[h] = value
    if sum(parsed_counts.values()) != groups:
        raise MixedResidencyBenchmarkError("histogram count sum mismatch")

    by_h = {row["gpu_hits"]: row for row in summary["cases"]}
    weighted_ms = sum(
        parsed_counts[h] * by_h[h]["median_ms"] for h in _EXPECTED_H
    ) / groups
    all_cpu_ms = summary["all_cpu_median_ms"]

    return {
        "schema": "tesy.mixed_residency_trace_weighted_diagnostic.v1",
        "classification": "TRACE_WEIGHTED_MEASURED_COMPONENT_DIAGNOSTIC",
        "status": "PASS",
        "routing_groups": groups,
        "histogram": {str(h): parsed_counts[h] for h in _EXPECTED_H},
        "weighted_median_case_ms": weighted_ms,
        "all_cpu_median_ms": all_cpu_ms,
        "ratio_vs_all_cpu": weighted_ms / all_cpu_ms,
        "speedup_equivalent_vs_all_cpu": all_cpu_ms / weighted_ms,
        "claim_boundary": (
            "Arithmetic weighting of separately measured isolated-case medians by "
            "a trace-derived ideal timely-insertion residency histogram. This is "
            "not a measured mixed full-model runtime, cache implementation, "
            "prefetch accuracy, concurrency result or physical memory traffic."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--input", required=True, type=Path)
    validate.add_argument("--output", required=True, type=Path)

    weight = sub.add_parser("weight")
    weight.add_argument("--summary", required=True, type=Path)
    weight.add_argument("--histogram", required=True, type=Path)
    weight.add_argument("--output", required=True, type=Path)

    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to replace {args.output}")

    if args.command == "validate":
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SystemExit("raw Stage B JSON must be an object")
        result = validate_mixed_residency_raw(payload)
    else:
        summary = json.loads(args.summary.read_text(encoding="utf-8"))
        histogram = json.loads(args.histogram.read_text(encoding="utf-8"))
        if not isinstance(summary, dict) or not isinstance(histogram, dict):
            raise SystemExit("summary/histogram must be JSON objects")
        result = weighted_trace_diagnostic(summary, histogram)

    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
