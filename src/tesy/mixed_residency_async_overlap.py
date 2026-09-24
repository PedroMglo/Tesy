from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any

from tesy.mixed_residency_overlap_bound import (
    MixedResidencyOverlapBoundError,
    _finite,
    _validate_stats,
    validate_overlap_bound_raw,
)


_ASYNC_GO_RATIO = 0.90
_EXPECTED_H = [0, 1, 2, 3, 4]


def _validate_parity(payload: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("status") != "PASS":
        raise MixedResidencyOverlapBoundError(f"{label} did not PASS")
    for field in ("max_abs", "max_abs_ref", "relative_max", "cosine"):
        _finite(payload.get(field), label=f"{label}.{field}")
    if payload["relative_max"] > 0.005 or payload["cosine"] < 0.9999:
        raise MixedResidencyOverlapBoundError(
            f"{label} threshold violated"
        )
    return payload


def validate_async_raw(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema") != "tesy.mixed_residency_async_raw.v1":
        raise MixedResidencyOverlapBoundError("unsupported async overlap schema")
    if (
        payload.get("classification")
        != "MEASURED_MIXED_RESIDENCY_ASYNC_DIAGNOSTIC"
    ):
        raise MixedResidencyOverlapBoundError(
            "unexpected async overlap classification"
        )
    if payload.get("gpu_async_capable") is not True:
        raise MixedResidencyOverlapBoundError(
            "GPU backend must advertise async capability"
        )
    if not isinstance(payload.get("cpu_async_capable"), bool):
        raise MixedResidencyOverlapBoundError(
            "cpu_async_capable must be boolean"
        )

    serial_payload = copy.deepcopy(payload)
    serial_payload["schema"] = "tesy.mixed_residency_overlap_bound_raw.v1"
    serial_payload["classification"] = (
        "MEASURED_MIXED_RESIDENCY_COMPONENT_DIAGNOSTIC"
    )
    serial_summary = validate_overlap_bound_raw(serial_payload)

    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) != 5:
        raise MixedResidencyOverlapBoundError("async cases must contain h=0..4")
    samples = payload["samples"]

    rows: list[dict[str, Any]] = []
    for raw_row, serial_row in zip(raw_cases, serial_summary["cases"], strict=True):
        h = serial_row["gpu_hits"]
        if raw_row.get("gpu_hits") != h:
            raise MixedResidencyOverlapBoundError(
                f"async case order mismatch for h={h}"
            )

        async_wall = raw_row.get("async_wall")
        async_parity = raw_row.get("async_parity")
        if 0 < h < 4:
            stats = _validate_stats(
                async_wall,
                label=f"h{h}.async_wall",
                expected_samples=samples,
            )
            parity = _validate_parity(
                async_parity,
                label=f"h{h}.async_parity",
            )
            async_median = float(stats["median_ms"])
            effective_median = async_median
        else:
            if async_wall is not None:
                raise MixedResidencyOverlapBoundError(
                    f"h{h}.async_wall must be null for serial anchor"
                )
            if async_parity is not None:
                raise MixedResidencyOverlapBoundError(
                    f"h{h}.async_parity must be null for serial anchor"
                )
            stats = None
            parity = None
            async_median = None
            effective_median = float(serial_row["direct_median_ms"])

        serial_median = float(serial_row["direct_median_ms"])
        rows.append(
            {
                "gpu_hits": h,
                "cpu_misses": 4 - h,
                "serial_median_ms": serial_median,
                "serial_p95_ms": serial_row["direct_p95_ms"],
                "async_median_ms": async_median,
                "effective_candidate_median_ms": effective_median,
                "async_speedup_vs_serial": (
                    serial_median / effective_median
                ),
                "serial_parity": serial_row["parity"],
                "async_parity": parity,
                "async_stats": stats,
            }
        )

    return {
        "schema": "tesy.mixed_residency_async_summary.v1",
        "classification": "MEASURED_MIXED_RESIDENCY_ASYNC_DIAGNOSTIC",
        "status": "PASS",
        "samples": samples,
        "gpu_async_capable": True,
        "cpu_async_capable": payload["cpu_async_capable"],
        "cpu_weight_buffer_type": serial_summary["cpu_weight_buffer_type"],
        "cpu_bias_buffer_type": serial_summary["cpu_bias_buffer_type"],
        "cases": rows,
        "claim_boundary": (
            "Same-campaign isolated serial and post-D2H CPU/GPU-overlap timings. "
            "Only h=1..3 execute the async candidate; h=0/h=4 retain measured "
            "serial anchors. This is not full-model throughput, cache behavior, "
            "prefetch, or physical PCIe/DRAM/NVMe traffic."
        ),
    }


def weight_async(
    summary: dict[str, Any],
    histogram: dict[str, Any],
) -> dict[str, Any]:
    if summary.get("schema") != "tesy.mixed_residency_async_summary.v1":
        raise MixedResidencyOverlapBoundError(
            "unsupported async summary schema"
        )
    if summary.get("status") != "PASS":
        raise MixedResidencyOverlapBoundError("async summary did not PASS")
    if histogram.get("schema") != "tesy.mixed_residency_hit_histogram.v1":
        raise MixedResidencyOverlapBoundError("unsupported histogram schema")
    if (
        histogram.get("classification")
        != "TRACE_DERIVED_RESIDENCY_OPPORTUNITY"
    ):
        raise MixedResidencyOverlapBoundError(
            "unexpected histogram classification"
        )

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
    if set(by_h) != set(_EXPECTED_H):
        raise MixedResidencyOverlapBoundError(
            "async summary must contain h=0..4"
        )

    weighted_serial = sum(
        parsed[h] * by_h[h]["serial_median_ms"] for h in _EXPECTED_H
    ) / groups
    weighted_async = sum(
        parsed[h] * by_h[h]["effective_candidate_median_ms"]
        for h in _EXPECTED_H
    ) / groups
    if not math.isfinite(weighted_serial) or weighted_serial <= 0:
        raise MixedResidencyOverlapBoundError(
            "weighted serial timing must be positive and finite"
        )
    if not math.isfinite(weighted_async) or weighted_async <= 0:
        raise MixedResidencyOverlapBoundError(
            "weighted async timing must be positive and finite"
        )

    gate_max_async_ms = _ASYNC_GO_RATIO * weighted_serial
    decision = (
        "ASYNC_OVERLAP_MEASURED_GO"
        if weighted_async <= gate_max_async_ms
        else "ASYNC_OVERLAP_COMPLEXITY_NO_GO"
    )

    return {
        "schema": "tesy.mixed_residency_async_weighted.v1",
        "classification": "TRACE_WEIGHTED_ASYNC_OVERLAP_DIAGNOSTIC",
        "status": "PASS",
        "routing_groups": groups,
        "histogram": {str(h): parsed[h] for h in _EXPECTED_H},
        "weighted_serial_median_ms": weighted_serial,
        "weighted_async_median_ms": weighted_async,
        "async_speedup_vs_serial": weighted_serial / weighted_async,
        "async_reduction_fraction": 1.0 - weighted_async / weighted_serial,
        "implementation_gate_ratio": _ASYNC_GO_RATIO,
        "implementation_gate_max_async_ms": gate_max_async_ms,
        "decision": decision,
        "claim_boundary": (
            "Arithmetic weighting of same-campaign measured isolated serial "
            "and async case medians by the admitted trace-derived residency "
            "histogram. It is not measured full-model latency or throughput."
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
            raise SystemExit("raw async JSON must be an object")
        result = validate_async_raw(payload)
    else:
        summary = json.loads(args.summary.read_text(encoding="utf-8"))
        histogram = json.loads(args.histogram.read_text(encoding="utf-8"))
        if not isinstance(summary, dict) or not isinstance(histogram, dict):
            raise SystemExit("summary/histogram must be JSON objects")
        result = weight_async(summary, histogram)

    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
