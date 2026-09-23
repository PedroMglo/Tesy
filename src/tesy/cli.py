from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tesy.backend import BackendError, probe_llama_cpp
from tesy.doctor import collect_snapshot
from tesy.models import (
    ModelLockError,
    get_model,
    inspect_model_file,
    load_lock,
    verify_model_file,
)
from tesy.planner import GIB, plan_capacity
from tesy.rawtrace import RawTraceError, read_raw_jsonl, summarize_raw
from tesy.simulator import simulate_demand_lru
from tesy.trace import TraceError, read_jsonl, summarize, window_union_metrics


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _parse_windows(raw: str) -> list[int]:
    windows: list[int] = []
    for item in raw.split(","):
        try:
            value = int(item)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"invalid window: {item}") from exc
        if value <= 0:
            raise argparse.ArgumentTypeError("windows must be positive")
        windows.append(value)
    if not windows:
        raise argparse.ArgumentTypeError("at least one window is required")
    return windows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tesy",
        description="Tesy research and feasibility tooling",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser(
        "doctor", help="inspect the live host without opening a model"
    )
    doctor.add_argument("--disk-path", type=Path, default=None)

    backend = sub.add_parser("backend", help="probe pinned backend provenance")
    backend_sub = backend.add_subparsers(dest="backend_command", required=True)
    probe = backend_sub.add_parser("probe", help="probe a llama.cpp binary")
    probe.add_argument("--binary", required=True, type=Path)
    probe.add_argument("--source-dir", type=Path, default=None)
    probe.add_argument("--backend-id", default="llama-cpp-stock")

    models = sub.add_parser("models", help="inspect and verify model candidates")
    model_sub = models.add_subparsers(dest="models_command", required=True)
    model_sub.add_parser("list", help="list model lock entries")
    inspect = model_sub.add_parser("inspect", help="inspect a local model file")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--sha256", action="store_true")
    verify = model_sub.add_parser("verify", help="verify a locked model artifact")
    verify.add_argument("model_id")
    verify.add_argument("path", type=Path)

    plan = sub.add_parser(
        "plan", help="produce a conservative static capacity admission"
    )
    plan.add_argument("--model", required=True)
    plan.add_argument("--path", type=Path, default=None)

    trace = sub.add_parser("trace", help="analyze routing traces")
    trace_sub = trace.add_subparsers(dest="trace_command", required=True)

    trace_summary = trace_sub.add_parser(
        "summarize", help="summarize normalized expert-byte traces"
    )
    trace_summary.add_argument("path", type=Path)
    trace_summary.add_argument(
        "--windows", type=_parse_windows, default=[1, 2, 4, 8]
    )

    raw_summary = trace_sub.add_parser(
        "raw-summary", help="validate passive router-ID traces"
    )
    raw_summary.add_argument("path", type=Path)
    raw_summary.add_argument("--expected-layers", type=int, default=None)
    raw_summary.add_argument("--expected-top-k", type=int, default=None)
    raw_summary.add_argument("--expected-experts", type=int, default=None)

    simulate = sub.add_parser(
        "simulate", help="replay a normalized routing trace through caches"
    )
    simulate.add_argument("--trace", required=True, type=Path)
    simulate.add_argument("--ram-cache-gib", required=True, type=float)
    simulate.add_argument("--vram-cache-gib", required=True, type=float)
    simulate.add_argument(
        "--phase", choices=["prefill", "decode"], default="decode"
    )

    report = sub.add_parser(
        "report", help="validate and pretty-print a JSON result"
    )
    report.add_argument("path", type=Path)

    return parser


def _optional_non_negative(value: int | None, field: str) -> int | None:
    if value is not None and value < 0:
        raise ValueError(f"{field} must be non-negative")
    return value


def _run(args: argparse.Namespace) -> int:
    if args.command == "doctor":
        _print(collect_snapshot(args.disk_path))
        return 0

    if args.command == "backend" and args.backend_command == "probe":
        result = probe_llama_cpp(
            args.binary,
            source_dir=args.source_dir,
            backend_id=args.backend_id,
        )
        _print(result)
        return 0 if result["status"] == "PASS" else 2

    if args.command == "models":
        lock = load_lock()
        if args.models_command == "list":
            _print(
                [
                    {
                        "id": model["id"],
                        "status": model["status"],
                        "purpose": model["purpose"],
                    }
                    for model in lock["models"]
                ]
            )
            return 0
        if args.models_command == "inspect":
            _print(inspect_model_file(args.path, with_sha256=args.sha256))
            return 0
        if args.models_command == "verify":
            model = get_model(lock, args.model_id)
            result = verify_model_file(model, args.path)
            _print(result)
            return 0 if result["status"] == "PASS" else 2

    if args.command == "plan":
        lock = load_lock()
        model = get_model(lock, args.model)
        snapshot = collect_snapshot(args.path.parent if args.path else None)
        artifact_bytes = None
        if args.path is not None:
            artifact_bytes = inspect_model_file(
                args.path, with_sha256=False
            )["size_bytes"]
        _print(plan_capacity(model, snapshot, artifact_bytes))
        return 0

    if args.command == "trace" and args.trace_command == "summarize":
        events = read_jsonl(args.path)
        payload = {
            "summary": summarize(events),
            "speculative_windows": [
                window_union_metrics(events, window) for window in args.windows
            ],
        }
        _print(payload)
        return 0

    if args.command == "trace" and args.trace_command == "raw-summary":
        expected_layers = _optional_non_negative(
            args.expected_layers, "expected_layers"
        )
        expected_top_k = _optional_non_negative(
            args.expected_top_k, "expected_top_k"
        )
        expected_experts = _optional_non_negative(
            args.expected_experts, "expected_experts"
        )
        result = summarize_raw(
            read_raw_jsonl(args.path),
            expected_layers=expected_layers,
            expected_top_k=expected_top_k,
            expected_experts=expected_experts,
        )
        _print(result)
        return 0 if result["status"] == "PASS" else 2

    if args.command == "simulate":
        if args.ram_cache_gib < 0 or args.vram_cache_gib < 0:
            raise ValueError("cache sizes must be non-negative")
        events = read_jsonl(args.trace)
        result = simulate_demand_lru(
            events,
            ram_cache_bytes=int(args.ram_cache_gib * GIB),
            vram_cache_bytes=int(args.vram_cache_gib * GIB),
            phase=args.phase,
        )
        _print(result)
        return 0

    if args.command == "report":
        payload = json.loads(args.path.read_text(encoding="utf-8"))
        _print(payload)
        return 0

    raise RuntimeError("unreachable command")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except (
        BackendError,
        ModelLockError,
        RawTraceError,
        TraceError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"tesy: error: {exc}", file=sys.stderr)
        return 2
