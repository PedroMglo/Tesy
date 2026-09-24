from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


class MixedResidencyOverlapBoundError(ValueError):
    pass


_EXPECTED_H = [0, 1, 2, 3, 4]
_EXPECTED_EXPERT_IDS = [0, 1, 2, 3]
_EXPECTED_MIX = [0.25, 0.25, 0.25, 0.25]


def _finite(value: Any, *, label: str, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MixedResidencyOverlapBoundError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise MixedResidencyOverlapBoundError(f"{label} must be finite")
    if positive and number <= 0:
        raise MixedResidencyOverlapBoundError(f"{label} must be positive")
    return number


def _validate_stats(payload: Any, *, label: str, expected_samples: int) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise MixedResidencyOverlapBoundError(f"{label} must be an object")
    samples = payload.get("samples_ms")
    if not isinstance(samples, list) or len(samples) != expected_samples:
        raise MixedResidencyOverlapBoundError(
            f"{label}.samples_ms must contain {expected_samples} samples"
        )
    values = [
        _finite(item, label=f"{label}.samples_ms", positive=True)
        for item in samples
    ]
    for field in ("median_ms", "p95_ms", "min_ms", "max_ms", "mean_ms"):
        _finite(payload.get(field), label=f"{label}.{field}", positive=True)
    if payload["min_ms"] != min(values) or payload["max_ms"] != max(values):
        raise MixedResidencyOverlapBoundError(
            f"{label} min/max do not match raw samples"
        )
    if not payload["min_ms"] <= payload["median_ms"] <= payload["max_ms"]:
        raise MixedResidencyOverlapBoundError(
            f"{label} median outside min/max"
        )
    if payload["p95_ms"] > payload["max_ms"]:
        raise MixedResidencyOverlapBoundError(
            f"{label} p95 exceeds max"
        )
    return payload


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-9)


def validate_overlap_bound_raw(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != "tesy.mixed_residency_overlap_bound_raw.v1":
        raise MixedResidencyOverlapBoundError("unsupported overlap-bound schema")
    if (
        payload.get("classification")
        != "MEASURED_MIXED_RESIDENCY_COMPONENT_DIAGNOSTIC"
    ):
        raise MixedResidencyOverlapBoundError(
            "unexpected overlap-bound classification"
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
            raise MixedResidencyOverlapBoundError(
                f"{field} mismatch: {payload.get(field)!r} != {value!r}"
            )

    for field in ("cpu_weight_buffer_type", "cpu_bias_buffer_type"):
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            raise MixedResidencyOverlapBoundError(
                f"{field} must be a non-empty string"
            )

    samples = payload.get("samples")
    if isinstance(samples, bool) or not isinstance(samples, int) or samples < 5:
        raise MixedResidencyOverlapBoundError("samples must be an integer >= 5")

    cases = payload.get("cases")
    if not isinstance(cases, list) or [row.get("gpu_hits") for row in cases] != _EXPECTED_H:
        raise MixedResidencyOverlapBoundError("cases must contain h=0..4 in order")

    rows: list[dict[str, Any]] = []
    for row in cases:
        h = row["gpu_hits"]
        cpu_misses = 4 - h
        if row.get("cpu_misses") != cpu_misses:
            raise MixedResidencyOverlapBoundError(
                f"cpu_misses mismatch for h={h}"
            )
        if row.get("source_expert_ids") != _EXPECTED_EXPERT_IDS:
            raise MixedResidencyOverlapBoundError(
                f"expert IDs mismatch for h={h}"
            )
        if row.get("global_mix_weight") != 0.25:
            raise MixedResidencyOverlapBoundError(
                f"mix weight mismatch for h={h}"
            )

        direct = _validate_stats(
            row.get("direct_wall"),
            label=f"h{h}.direct_wall",
            expected_samples=samples,
        )

        components = row.get("components")
        if not isinstance(components, dict):
            raise MixedResidencyOverlapBoundError(
                f"components must be an object for h={h}"
            )

        expected_presence = {
            "activation_d2h": cpu_misses > 0,
            "cpu_compute": cpu_misses > 0,
            "gpu_compute": h > 0,
            "cpu_partial_h2d": cpu_misses > 0,
            "gpu_aggregation": 0 < h < 4,
        }
        medians: dict[str, float | None] = {}
        for name, present in expected_presence.items():
            value = components.get(name)
            if present:
                stats = _validate_stats(
                    value,
                    label=f"h{h}.components.{name}",
                    expected_samples=samples,
                )
                medians[name] = float(stats["median_ms"])
            else:
                if value is not None:
                    raise MixedResidencyOverlapBoundError(
                        f"h{h}.components.{name} must be null"
                    )
                medians[name] = None

        parity = row.get("parity")
        if not isinstance(parity, dict) or parity.get("status") != "PASS":
            raise MixedResidencyOverlapBoundError(
                f"numerical parity did not PASS for h={h}"
            )
        for field in ("max_abs", "max_abs_ref", "relative_max", "cosine"):
            _finite(parity.get(field), label=f"h{h}.parity.{field}")
        if parity["relative_max"] > 0.005 or parity["cosine"] < 0.9999:
            raise MixedResidencyOverlapBoundError(
                f"parity threshold violated for h={h}"
            )

        if 0 < h < 4:
            component_sum = (
                medians["activation_d2h"]
                + medians["cpu_compute"]
                + medians["gpu_compute"]
                + medians["cpu_partial_h2d"]
                + medians["gpu_aggregation"]
            )
            overlap_bound = (
                medians["activation_d2h"]
                + max(medians["cpu_compute"], medians["gpu_compute"])
                + medians["cpu_partial_h2d"]
                + medians["gpu_aggregation"]
            )
            dominating_branch = (
                "CPU"
                if medians["cpu_compute"] >= medians["gpu_compute"]
                else "GPU"
            )
        elif h == 0:
            component_sum = (
                medians["activation_d2h"]
                + medians["cpu_compute"]
                + medians["cpu_partial_h2d"]
            )
            overlap_bound = component_sum
            dominating_branch = "CPU_ONLY"
        else:
            component_sum = medians["gpu_compute"]
            overlap_bound = component_sum
            dominating_branch = "GPU_ONLY"

        observed_component_sum = _finite(
            row.get("component_sum_median_ms"),
            label=f"h{h}.component_sum_median_ms",
            positive=True,
        )
        observed_bound = _finite(
            row.get("post_d2h_overlap_bound_median_ms"),
            label=f"h{h}.post_d2h_overlap_bound_median_ms",
            positive=True,
        )
        observed_speedup = _finite(
            row.get("overlap_bound_speedup_vs_direct"),
            label=f"h{h}.overlap_bound_speedup_vs_direct",
            positive=True,
        )

        if not _close(observed_component_sum, component_sum):
            raise MixedResidencyOverlapBoundError(
                f"component sum mismatch for h={h}"
            )
        if not _close(observed_bound, overlap_bound):
            raise MixedResidencyOverlapBoundError(
                f"overlap bound mismatch for h={h}"
            )
        expected_speedup = float(direct["median_ms"]) / overlap_bound
        if not _close(observed_speedup, expected_speedup):
            raise MixedResidencyOverlapBoundError(
                f"overlap-bound speedup mismatch for h={h}"
            )

        rows.append(
            {
                "gpu_hits": h,
                "cpu_misses": cpu_misses,
                "direct_median_ms": direct["median_ms"],
                "direct_p95_ms": direct["p95_ms"],
                "component_median_ms": medians,
                "component_sum_median_ms": component_sum,
                "post_d2h_overlap_bound_median_ms": overlap_bound,
                "overlap_bound_speedup_vs_direct": expected_speedup,
                "dominating_compute_branch": dominating_branch,
                "parity": parity,
            }
        )

    return {
        "schema": "tesy.mixed_residency_overlap_bound_summary.v1",
        "classification": "MEASURED_MIXED_RESIDENCY_COMPONENT_DIAGNOSTIC",
        "status": "PASS",
        "samples": samples,
        "cpu_weight_buffer_type": payload["cpu_weight_buffer_type"],
        "cpu_bias_buffer_type": payload["cpu_bias_buffer_type"],
        "cases": rows,
        "claim_boundary": (
            "Component timings are measured separately from the direct serial path. "
            "The overlap bound assumes CPU and GPU subset compute can overlap only "
            "after the input D2H copy completes; D2H, CPU-partial H2D and GPU "
            "aggregation remain serialized. It is not a measured async execution."
        ),
    }


def weight_overlap_bound(
    summary: dict[str, Any],
    histogram: dict[str, Any],
) -> dict[str, Any]:
    if summary.get("schema") != "tesy.mixed_residency_overlap_bound_summary.v1":
        raise MixedResidencyOverlapBoundError("unsupported overlap summary schema")
    if summary.get("status") != "PASS":
        raise MixedResidencyOverlapBoundError("overlap summary did not PASS")
    if histogram.get("schema") != "tesy.mixed_residency_hit_histogram.v1":
        raise MixedResidencyOverlapBoundError("unsupported histogram schema")

    groups = histogram.get("routing_groups")
    counts = histogram.get("gpu_resident_experts_per_top4_histogram")
    if isinstance(groups, bool) or not isinstance(groups, int) or groups <= 0:
        raise MixedResidencyOverlapBoundError("invalid routing_groups")
    if not isinstance(counts, dict) or set(counts) != {"0", "1", "2", "3", "4"}:
        raise MixedResidencyOverlapBoundError("invalid grouped histogram")

    parsed: dict[int, int] = {}
    for h in _EXPECTED_H:
        value = counts.get(str(h))
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise MixedResidencyOverlapBoundError(
                f"invalid histogram count h={h}"
            )
        parsed[h] = value
    if sum(parsed.values()) != groups:
        raise MixedResidencyOverlapBoundError("histogram count sum mismatch")

    by_h = {row["gpu_hits"]: row for row in summary["cases"]}
    weighted_direct = sum(
        parsed[h] * by_h[h]["direct_median_ms"] for h in _EXPECTED_H
    ) / groups
    weighted_bound = sum(
        parsed[h] * by_h[h]["post_d2h_overlap_bound_median_ms"]
        for h in _EXPECTED_H
    ) / groups

    return {
        "schema": "tesy.mixed_residency_overlap_bound_weighted.v1",
        "classification": "TRACE_WEIGHTED_OVERLAP_BOUND_DIAGNOSTIC",
        "status": "PASS",
        "routing_groups": groups,
        "histogram": {str(h): parsed[h] for h in _EXPECTED_H},
        "weighted_direct_median_ms": weighted_direct,
        "weighted_post_d2h_overlap_bound_ms": weighted_bound,
        "bound_speedup_vs_weighted_direct": weighted_direct / weighted_bound,
        "claim_boundary": (
            "Arithmetic weighting of separately measured case medians and a "
            "trace-derived residency-opportunity histogram. The overlap value is "
            "a post-D2H compute-overlap bound, not measured concurrent execution "
            "or full-model latency."
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
            raise SystemExit("raw overlap-bound JSON must be an object")
        result = validate_overlap_bound_raw(payload)
    else:
        summary = json.loads(args.summary.read_text(encoding="utf-8"))
        histogram = json.loads(args.histogram.read_text(encoding="utf-8"))
        if not isinstance(summary, dict) or not isinstance(histogram, dict):
            raise SystemExit("summary/histogram must be JSON objects")
        result = weight_overlap_bound(summary, histogram)

    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
