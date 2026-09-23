from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tesy.backend import BackendError, probe_llama_cpp
from tesy.doctor import collect_snapshot
from tesy.headroom import native_cache_headroom
from tesy.models import (
    ModelLockError,
    get_model,
    inspect_model_file,
    load_lock,
    verify_model_file,
)
from tesy.native_trace import NativeTraceError, read_native_jsonl, summarize_native
from tesy.planner import GIB, plan_capacity
from tesy.simulator import simulate_demand_lru
from tesy.trace import TraceError, read_jsonl, summarize, window_union_metrics


def _print(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _parse_int_list(raw: str, label: str, minimum: int) -> list[int]:
    values: list[int] = []
    for item in raw.split(","):
        try:
            value = int(item)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"invalid {label}: {item}") from exc
        if value < minimum:
            raise argparse.ArgumentTypeError(
                f"{label} values must be >= {minimum}"
            )
        values.append(value)
    if not values:
        raise argparse.ArgumentTypeError(f"at least one {label} is required")
    return values


def _parse_windows(raw: str) -> list[int]:
    return _parse_int_list(raw, "window", 1)


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

    trace = sub.add_parser("trace", help="analyze normalized routing traces")
    trace_sub = trace.add_subparsers(dest="trace_command", required=True)
    trace_summary = trace_sub.add_parser("summarize")
    trace_summary.add_argument("path", type=Path)
    trace_summary.add_argument(
        "--windows", type=_parse_windows, default=[1, 2, 4, 8]
    )
    native_summary = trace_sub.add_parser(
        "summarize-native", help="summarize raw llama.cpp MoE top-k traces"
    )
    native_summary.add_argument("path", type=Path)
    native_headroom = trace_sub.add_parser(
        "headroom-native",
        help="estimate count-space cache headroom from one-token graph traces",
    )
    native_headroom.add_argument("path", type=Path)
    native_headroom.add_argument(
        "--slots",
        type=lambda raw: _parse_int_list(raw, "slot", 0),
        default=[0, 32, 64, 128],
    )
    native_headroom.add_argument("--min-graph-seq", type=int, default=0)

    simulate = sub.add_parser(
        "simulate", help="replay a routing trace through caches"
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

    if args.command == "trace" and args.trace_command == "summarize-native":
        _print(summarize_native(read_native_jsonl(args.path)))
        return 0

    if args.command == "trace" and args.trace_command == "headroom-native":
        _print(
            native_cache_headroom(
                read_native_jsonl(args.path),
                args.slots,
                min_graph_seq=args.min_graph_seq,
            )
        )
        return 0

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
        NativeTraceError,
        TraceError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"tesy: error: {exc}", file=sys.stderr)
        return 2
