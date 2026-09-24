from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tesy.crossover_provenance import (
    CrossoverProvenanceError,
    collect_crossover_provenance,
)


class MixedResidencyProvenanceError(ValueError):
    pass


def collect_mixed_residency_provenance(
    *,
    pid: int,
    expected_executable: Path,
    build_dir: Path,
    expected_argv_path: Path,
) -> dict[str, Any]:
    try:
        payload = collect_crossover_provenance(
            pid=pid,
            expected_executable=expected_executable,
            build_dir=build_dir,
            expected_argv_path=expected_argv_path,
        )
    except CrossoverProvenanceError as exc:
        raise MixedResidencyProvenanceError(str(exc)) from exc

    payload = dict(payload)
    payload["schema"] = "tesy.mixed_residency_runtime_provenance.v1"
    payload["claim_boundary"] = (
        "PASS binds the live mixed-residency microbenchmark to the expected "
        "executable, exact argv and the single selected libggml-cuda artifact. "
        "It does not establish numerical parity, timing quality, cache behavior "
        "or physical memory traffic."
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--expected-executable", required=True, type=Path)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--expected-argv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to replace {args.output}")

    payload = collect_mixed_residency_provenance(
        pid=args.pid,
        expected_executable=args.expected_executable,
        build_dir=args.build_dir,
        expected_argv_path=args.expected_argv,
    )
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
