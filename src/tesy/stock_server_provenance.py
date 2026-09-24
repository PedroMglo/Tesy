"""Bind a stock llama-server run to its exact process and mapped CUDA backend."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from tesy.crossover_provenance import collect_crossover_provenance


def collect_stock_server_provenance(
    *,
    pid: int,
    expected_executable: Path,
    build_dir: Path,
    expected_argv_path: Path,
    attempts: int = 100,
    sleep_seconds: float = 0.1,
) -> dict:
    if attempts <= 0:
        raise ValueError("attempts must be positive")
    last = None
    for _ in range(attempts):
        last = collect_crossover_provenance(
            pid=pid,
            expected_executable=expected_executable,
            build_dir=build_dir,
            expected_argv_path=expected_argv_path,
        )
        if last["status"] == "PASS":
            last["schema"] = "tesy.full_model_stock_server_runtime_provenance.v1"
            last["claim_boundary"] = (
                "PASS binds the stock server process to exact executable, argv and the "
                "single mapped build CUDA backend before the generation request. "
                "It does not establish correctness or performance quality."
            )
            return last
        time.sleep(sleep_seconds)
    raise ValueError(f"stock server runtime provenance failed: {last['mismatches']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--expected-executable", required=True, type=Path)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--expected-argv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = collect_stock_server_provenance(
        pid=args.pid,
        expected_executable=args.expected_executable,
        build_dir=args.build_dir,
        expected_argv_path=args.expected_argv,
    )
    with args.output.open("x") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    main()
