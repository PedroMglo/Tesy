from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path

MIB = 1024 * 1024


class PlacementCapacityError(ValueError):
    pass


def parse_fitted_cli(text: str, *, expected_ctx: int) -> dict:
    candidates = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("-c ")
    ]
    if len(candidates) != 1:
        raise PlacementCapacityError(
            f"expected exactly one fitted CLI line starting with '-c ', got {len(candidates)}"
        )

    argv = shlex.split(candidates[0])
    if len(argv) % 2 != 0:
        raise PlacementCapacityError("fitted CLI must contain flag/value pairs")

    allowed = {
        "-c": "ctx_size",
        "-ngl": "n_gpu_layers",
        "-ts": "tensor_split",
        "-ot": "override_tensor",
    }
    parsed: dict[str, object] = {}
    for index in range(0, len(argv), 2):
        flag = argv[index]
        value = argv[index + 1]
        key = allowed.get(flag)
        if key is None:
            raise PlacementCapacityError(f"unexpected fitted CLI flag: {flag}")
        if key in parsed:
            raise PlacementCapacityError(f"duplicate fitted CLI field: {key}")
        if key in {"ctx_size", "n_gpu_layers"}:
            try:
                parsed[key] = int(value)
            except ValueError as exc:
                raise PlacementCapacityError(
                    f"{flag} must have an integer value"
                ) from exc
        else:
            if not value:
                raise PlacementCapacityError(f"{flag} must not be empty")
            parsed[key] = value

    if "ctx_size" not in parsed or "n_gpu_layers" not in parsed:
        raise PlacementCapacityError("fitted CLI must contain -c and -ngl")
    if parsed["ctx_size"] != expected_ctx:
        raise PlacementCapacityError(
            f"fitter changed frozen context: {parsed['ctx_size']} != {expected_ctx}"
        )

    return {
        "schema": "tesy.llama_fit_args.v1",
        "classification": "SOURCE_BACKED_FITTED_PLACEMENT",
        "argv": argv,
        **parsed,
        "claim_boundary": (
            "Arguments were emitted by the pinned llama-fit-params utility. "
            "They freeze a stock placement choice; they are not a performance measurement."
        ),
    }


def parse_fit_print(text: str) -> dict[str, dict[str, int]]:
    rows: dict[str, dict[str, int]] = {}
    for raw in text.splitlines():
        parts = raw.strip().split()
        if len(parts) != 4:
            continue
        name = parts[0]
        try:
            model_mib, context_mib, compute_mib = (int(value) for value in parts[1:])
        except ValueError:
            continue
        if min(model_mib, context_mib, compute_mib) < 0:
            raise PlacementCapacityError("negative memory estimate")
        if name in rows:
            raise PlacementCapacityError(f"duplicate memory-estimate row: {name}")
        rows[name] = {
            "model_mib": model_mib,
            "context_mib": context_mib,
            "compute_mib": compute_mib,
            "total_mib": model_mib + context_mib + compute_mib,
        }

    if "Host" not in rows:
        raise PlacementCapacityError("fit-print output is missing Host row")
    devices = [name for name in rows if name != "Host"]
    if len(devices) != 1:
        raise PlacementCapacityError(
            f"expected exactly one accelerator row, got {devices!r}"
        )
    return rows


def evaluate_capacity(
    text: str,
    *,
    gpu_free_bytes: int,
    mem_available_bytes: int,
    n_cpu_moe: int,
    gpu_target_mib: int = 1024,
    host_guard_mib: int = 2048,
    rounding_guard_mib: int = 16,
) -> dict:
    if gpu_free_bytes <= 0 or mem_available_bytes <= 0:
        raise PlacementCapacityError("available memory inputs must be positive")
    if n_cpu_moe < 0:
        raise PlacementCapacityError("n_cpu_moe must be non-negative")
    for name, value in {
        "gpu_target_mib": gpu_target_mib,
        "host_guard_mib": host_guard_mib,
        "rounding_guard_mib": rounding_guard_mib,
    }.items():
        if value < 0:
            raise PlacementCapacityError(f"{name} must be non-negative")

    rows = parse_fit_print(text)
    device_name = next(name for name in rows if name != "Host")
    device = rows[device_name]
    host = rows["Host"]
    gpu_free_mib = gpu_free_bytes // MIB
    mem_available_mib = mem_available_bytes // MIB

    gpu_required_mib = (
        device["total_mib"] + gpu_target_mib + rounding_guard_mib
    )
    host_required_mib = (
        host["total_mib"] + host_guard_mib + rounding_guard_mib
    )
    gpu_pass = gpu_required_mib <= gpu_free_mib
    host_pass = host_required_mib <= mem_available_mib

    reasons: list[str] = []
    if not gpu_pass:
        reasons.append("PROJECTED_GPU_HEADROOM")
    if not host_pass:
        reasons.append("PROJECTED_HOST_HEADROOM")

    return {
        "schema": "tesy.n_cpu_moe_capacity_estimate.v1",
        "classification": "SOURCE_BACKED_MEMORY_ESTIMATE",
        "n_cpu_moe": n_cpu_moe,
        "device": device_name,
        "rows": rows,
        "campaign_start_gpu_free_bytes": gpu_free_bytes,
        "campaign_start_mem_available_bytes": mem_available_bytes,
        "gpu_target_mib": gpu_target_mib,
        "host_guard_mib": host_guard_mib,
        "rounding_guard_mib": rounding_guard_mib,
        "gpu_required_mib": gpu_required_mib,
        "host_required_mib": host_required_mib,
        "gpu_pass": gpu_pass,
        "host_pass": host_pass,
        "admitted": gpu_pass and host_pass,
        "rejection_reasons": reasons,
        "claim_boundary": (
            "llama-fit-params --fit-print reports projected model/context/compute "
            "memory in integer MiB. This is an estimator-based admission gate, not "
            "measured VRAM/RAM traffic or proof that a subsequent run will fit."
        ),
    }


def _write_json_no_replace(path: Path, payload: dict) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    fitted = sub.add_parser("parse-fitted-cli")
    fitted.add_argument("--input", required=True, type=Path)
    fitted.add_argument("--expected-ctx", required=True, type=int)
    fitted.add_argument("--output", required=True, type=Path)

    estimate = sub.add_parser("evaluate-fit-print")
    estimate.add_argument("--input", required=True, type=Path)
    estimate.add_argument("--gpu-free-bytes", required=True, type=int)
    estimate.add_argument("--mem-available-bytes", required=True, type=int)
    estimate.add_argument("--n-cpu-moe", required=True, type=int)
    estimate.add_argument("--gpu-target-mib", type=int, default=1024)
    estimate.add_argument("--host-guard-mib", type=int, default=2048)
    estimate.add_argument("--rounding-guard-mib", type=int, default=16)
    estimate.add_argument("--output", required=True, type=Path)

    args = parser.parse_args()
    text = args.input.read_text(encoding="utf-8")

    if args.command == "parse-fitted-cli":
        payload = parse_fitted_cli(text, expected_ctx=args.expected_ctx)
    else:
        payload = evaluate_capacity(
            text,
            gpu_free_bytes=args.gpu_free_bytes,
            mem_available_bytes=args.mem_available_bytes,
            n_cpu_moe=args.n_cpu_moe,
            gpu_target_mib=args.gpu_target_mib,
            host_guard_mib=args.host_guard_mib,
            rounding_guard_mib=args.rounding_guard_mib,
        )

    _write_json_no_replace(args.output, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
