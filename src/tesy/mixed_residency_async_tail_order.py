from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from tesy.mixed_residency_async_overlap import validate_async_raw
from tesy.mixed_residency_overlap_bound import (
    MixedResidencyOverlapBoundError,
)


class MixedResidencyAsyncTailOrderError(ValueError):
    pass


_EXPECTED_SAMPLES = 81
_MEDIAN_GO_RATIO = 0.90
_P95_MAX_RATIO = 1.10
_GATED_H = {2, 3}


def _finite_samples(values: Any, *, label: str) -> list[float]:
    if not isinstance(values, list) or not values:
        raise MixedResidencyAsyncTailOrderError(
            f"{label} must be a non-empty sample list"
        )
    out: list[float] = []
    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MixedResidencyAsyncTailOrderError(
                f"{label}[{index}] must be numeric"
            )
        number = float(value)
        if not math.isfinite(number) or number <= 0:
            raise MixedResidencyAsyncTailOrderError(
                f"{label}[{index}] must be positive and finite"
            )
        out.append(number)
    return out


def _summary(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    p95_index = min(
        len(ordered) - 1,
        math.ceil(0.95 * len(ordered)) - 1,
    )
    return {
        "samples": len(ordered),
        "median_ms": ordered[len(ordered) // 2],
        "p95_ms": ordered[p95_index],
        "min_ms": ordered[0],
        "max_ms": ordered[-1],
        "mean_ms": sum(ordered) / len(ordered),
    }


def analyze_conditioned_case(
    serial_samples: list[float],
    async_samples: list[float],
    *,
    gpu_hits: int,
) -> dict[str, Any]:
    serial = _finite_samples(
        serial_samples,
        label=f"h{gpu_hits}.serial",
    )
    async_values = _finite_samples(
        async_samples,
        label=f"h{gpu_hits}.async",
    )
    if len(serial) != _EXPECTED_SAMPLES:
        raise MixedResidencyAsyncTailOrderError(
            f"h{gpu_hits}.serial must contain {_EXPECTED_SAMPLES} samples"
        )
    if len(async_values) != _EXPECTED_SAMPLES:
        raise MixedResidencyAsyncTailOrderError(
            f"h{gpu_hits}.async must contain {_EXPECTED_SAMPLES} samples"
        )

    # measure_paired() warmups end in async. During timed samples:
    # even i: serial block -> async block
    # odd i:  async block -> serial block
    # Therefore odd async samples are steady async-after-async observations,
    # while even async samples measure serial->async transitions. For serial,
    # sample 0 follows the final async warmup and is excluded from the
    # steady serial-after-serial bucket; even samples >= 2 are steady serial.
    async_after_serial = async_values[0::2]
    async_after_async = async_values[1::2]
    serial_after_async = serial[1::2]
    serial_after_serial = serial[2::2]

    if not (
        len(async_after_serial) == 41
        and len(async_after_async) == 40
        and len(serial_after_async) == 40
        and len(serial_after_serial) == 40
    ):
        raise MixedResidencyAsyncTailOrderError(
            f"h{gpu_hits} conditioned sample cardinality mismatch"
        )

    ss = _summary(serial_after_serial)
    aa = _summary(async_after_async)
    sa = _summary(async_after_serial)
    a_s = _summary(serial_after_async)

    steady_median_ratio = float(aa["median_ms"]) / float(ss["median_ms"])
    steady_p95_ratio = float(aa["p95_ms"]) / float(ss["p95_ms"])
    transition_p95_amplification = (
        float(sa["p95_ms"]) / float(aa["p95_ms"])
    )

    gated = gpu_hits in _GATED_H
    median_gate = (
        steady_median_ratio <= _MEDIAN_GO_RATIO
        if gated
        else None
    )
    p95_gate = (
        steady_p95_ratio <= _P95_MAX_RATIO
        if gated
        else None
    )

    return {
        "gpu_hits": gpu_hits,
        "gated": gated,
        "serial_after_serial": ss,
        "serial_after_async": a_s,
        "async_after_async": aa,
        "async_after_serial": sa,
        "steady_async_median_ratio_vs_serial": steady_median_ratio,
        "steady_async_p95_ratio_vs_serial": steady_p95_ratio,
        "serial_to_async_p95_amplification_vs_steady_async": (
            transition_p95_amplification
        ),
        "median_gate_max_ratio": _MEDIAN_GO_RATIO if gated else None,
        "p95_gate_max_ratio": _P95_MAX_RATIO if gated else None,
        "median_gate_pass": median_gate,
        "p95_gate_pass": p95_gate,
    }


def analyze_async_tail_order_raw(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        validated = validate_async_raw(payload)
    except MixedResidencyOverlapBoundError as exc:
        raise MixedResidencyAsyncTailOrderError(str(exc)) from exc

    if validated["samples"] != _EXPECTED_SAMPLES:
        raise MixedResidencyAsyncTailOrderError(
            f"tail-order campaign requires {_EXPECTED_SAMPLES} samples"
        )

    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise MixedResidencyAsyncTailOrderError("raw cases must be a list")
    by_h = {row.get("gpu_hits"): row for row in raw_cases}

    rows: list[dict[str, Any]] = []
    for h in (1, 2, 3):
        row = by_h.get(h)
        if not isinstance(row, dict):
            raise MixedResidencyAsyncTailOrderError(
                f"missing raw mixed case h={h}"
            )
        direct = row.get("direct_wall")
        async_wall = row.get("async_wall")
        if not isinstance(direct, dict) or not isinstance(async_wall, dict):
            raise MixedResidencyAsyncTailOrderError(
                f"missing timing objects for h={h}"
            )
        rows.append(
            analyze_conditioned_case(
                direct.get("samples_ms"),
                async_wall.get("samples_ms"),
                gpu_hits=h,
            )
        )

    gated_rows = [row for row in rows if row["gated"]]
    go = all(
        row["median_gate_pass"] is True
        and row["p95_gate_pass"] is True
        for row in gated_rows
    )
    decision = (
        "ASYNC_STEADY_TAIL_GO"
        if go
        else "ASYNC_STEADY_TAIL_NO_GO"
    )

    return {
        "schema": "tesy.mixed_residency_async_tail_order.v1",
        "classification": "MEASURED_ASYNC_ORDER_CONDITIONED_TAIL_DIAGNOSTIC",
        "status": "PASS",
        "samples": _EXPECTED_SAMPLES,
        "inner": payload.get("inner"),
        "gated_gpu_hits": sorted(_GATED_H),
        "median_gate_max_ratio": _MEDIAN_GO_RATIO,
        "p95_gate_max_ratio": _P95_MAX_RATIO,
        "cases": rows,
        "decision": decision,
        "claim_boundary": (
            "Order-conditioned analysis of the existing paired isolated-FFN "
            "benchmark. Odd async samples represent async-after-async steady "
            "observations and even async samples represent serial-to-async "
            "transitions under the frozen paired schedule. This does not "
            "measure routed-layer/full-model latency, cache behavior, prefetch, "
            "or physical PCIe/DRAM/NVMe traffic."
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
        raise SystemExit("raw async JSON must be an object")

    result = analyze_async_tail_order_raw(payload)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
