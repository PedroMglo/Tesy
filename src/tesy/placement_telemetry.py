from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from tesy.placement_capacity import PlacementCapacityError, parse_fit_print


class PlacementTelemetryError(ValueError):
    pass


_MODEL_BUFFER_RE = re.compile(
    r"(?P<name>\S+)\s+model buffer size\s*=\s*(?P<mib>[0-9]+(?:\.[0-9]+)?)\s+MiB"
)
_OFFLOAD_RE = re.compile(r"offloaded\s+(?P<loaded>\d+)/(?P<total>\d+)\s+layers to GPU")


def parse_server_model_buffers(text: str) -> dict:
    buffers: list[dict[str, object]] = []
    offload_rows: list[dict[str, int]] = []

    for raw in text.splitlines():
        match = _MODEL_BUFFER_RE.search(raw)
        if match:
            value = float(match.group("mib"))
            if value < 0:
                raise PlacementTelemetryError("negative model buffer size")
            buffers.append(
                {
                    "name": match.group("name"),
                    "mib": value,
                }
            )

        offload = _OFFLOAD_RE.search(raw)
        if offload:
            offload_rows.append(
                {
                    "loaded": int(offload.group("loaded")),
                    "total": int(offload.group("total")),
                }
            )

    if not buffers:
        raise PlacementTelemetryError("server log contains no model buffer sizes")
    if len(offload_rows) != 1:
        raise PlacementTelemetryError(
            f"expected exactly one offloaded-layers row, got {len(offload_rows)}"
        )

    gpu_names = sorted(
        {
            str(row["name"])
            for row in buffers
            if str(row["name"]).startswith("CUDA")
            and not str(row["name"]).startswith("CUDA_Host")
        }
    )
    if gpu_names != ["CUDA0"]:
        raise PlacementTelemetryError(
            f"expected only CUDA0 model buffers, got {gpu_names!r}"
        )

    gpu_buffers = [
        row for row in buffers if str(row["name"]).startswith("CUDA0")
    ]
    host_buffers = [
        row for row in buffers if not str(row["name"]).startswith("CUDA0")
    ]
    mapped_host_buffers = [
        row for row in host_buffers if "Mapped" in str(row["name"])
    ]

    return {
        "buffers": buffers,
        "gpu_model_mib": sum(float(row["mib"]) for row in gpu_buffers),
        "host_runtime_buffer_mib": sum(
            float(row["mib"]) for row in host_buffers
        ),
        "host_runtime_buffer_names": [
            str(row["name"]) for row in host_buffers
        ],
        "mapped_host_buffer_mib": sum(
            float(row["mib"]) for row in mapped_host_buffers
        ),
        "mapped_host_buffer_names": [
            str(row["name"]) for row in mapped_host_buffers
        ],
        "offloaded_layers": offload_rows[0],
    }


def validate_placement_telemetry(
    *,
    fit_print_text: str,
    server_stderr_text: str,
    placement_id: str,
    tolerance_mib: float = 2.0,
) -> dict:
    if not isinstance(placement_id, str) or not placement_id.strip():
        raise PlacementTelemetryError("placement_id must be non-empty")
    if tolerance_mib < 0:
        raise PlacementTelemetryError("tolerance_mib must be non-negative")

    try:
        projected = parse_fit_print(fit_print_text)
    except PlacementCapacityError as exc:
        raise PlacementTelemetryError(str(exc)) from exc

    device_names = [name for name in projected if name != "Host"]
    if device_names != ["CUDA0"]:
        raise PlacementTelemetryError(
            f"expected CUDA0 fit-print device, got {device_names!r}"
        )

    observed = parse_server_model_buffers(server_stderr_text)
    projected_gpu_mib = float(projected["CUDA0"]["model_mib"])
    projected_host_mib = float(projected["Host"]["model_mib"])
    gpu_delta_mib = observed["gpu_model_mib"] - projected_gpu_mib

    mismatches: list[str] = []
    if abs(gpu_delta_mib) > tolerance_mib:
        mismatches.append(
            "CUDA0 model buffer differs from fit-print projection: "
            f"{observed['gpu_model_mib']:.3f} vs {projected_gpu_mib:.3f} MiB"
        )

    if projected_host_mib > 0 and not observed["mapped_host_buffer_names"]:
        mismatches.append(
            "projected Host model allocation is non-zero but server log has "
            "no mmap-backed Host model buffer"
        )

    return {
        "schema": "tesy.stock_placement_telemetry.v2",
        "classification": "MEASURED_RUNTIME_PLACEMENT_LOG_DIAGNOSTIC",
        "status": "PASS" if not mismatches else "FAIL",
        "placement_id": placement_id,
        "gpu_tolerance_mib": tolerance_mib,
        "projected_logical_model_mib": {
            "CUDA0": projected_gpu_mib,
            "Host": projected_host_mib,
        },
        "observed_runtime_model_buffers": {
            "CUDA0_mib": observed["gpu_model_mib"],
            "Host_reported_buffer_mib": observed["host_runtime_buffer_mib"],
            "Host_reported_buffer_names": observed[
                "host_runtime_buffer_names"
            ],
            "Host_mmap_span_mib": observed["mapped_host_buffer_mib"],
            "Host_mmap_buffer_names": observed["mapped_host_buffer_names"],
        },
        "cuda0_delta_mib": gpu_delta_mib,
        "host_comparability": {
            "status": "NOT_COMPARABLE_MMAP_SPAN",
            "projected_quantity": "LOGICAL_TENSOR_ALLOCATION_MIB",
            "runtime_quantity": "MMAP_BUFFER_SPAN_MIB",
            "equality_gate": False,
            "reason": (
                "Pinned fit-print uses no_alloc with load_mode NONE and reports "
                "logical host tensor allocation. Stock mmap runtime reports a "
                "CPU_Mapped buffer spanning first-to-last mapped tensor offsets, "
                "which may include gaps and is not resident DRAM bytes."
            ),
        },
        "model_buffers": observed["buffers"],
        "offloaded_layers": observed["offloaded_layers"],
        "mismatches": mismatches,
        "claim_boundary": (
            "PASS verifies aggregate CUDA0 model-buffer parity against the "
            "same-placement fit-print projection and requires the expected "
            "mmap-backed Host buffer to be present when Host allocation is "
            "projected. The Host runtime buffer size is recorded but explicitly "
            "not compared with fit-print Host model MiB. Exact placement authority "
            "also requires the frozen live argv and pinned source/build provenance. "
            "No physical VRAM/DRAM/PCIe traffic claim follows."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fit-print", required=True, type=Path)
    parser.add_argument("--server-stderr", required=True, type=Path)
    parser.add_argument("--placement-id", required=True)
    parser.add_argument("--tolerance-mib", type=float, default=2.0)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to replace {args.output}")

    payload = validate_placement_telemetry(
        fit_print_text=args.fit_print.read_text(encoding="utf-8"),
        server_stderr_text=args.server_stderr.read_text(
            encoding="utf-8", errors="replace"
        ),
        placement_id=args.placement_id,
        tolerance_mib=args.tolerance_mib,
    )
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
