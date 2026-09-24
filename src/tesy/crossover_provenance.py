from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from tesy.runtime_provenance import parse_proc_cmdline, parse_proc_maps


class CrossoverProvenanceError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_argv(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CrossoverProvenanceError(
            f"cannot read expected argv {path}: {exc}"
        ) from exc
    if (
        not isinstance(payload, list)
        or not payload
        or any(not isinstance(value, str) or not value for value in payload)
    ):
        raise CrossoverProvenanceError(
            "expected argv must be a non-empty JSON string list"
        )
    return payload


def _find_cuda_backend(build_dir: Path) -> Path:
    try:
        build = build_dir.expanduser().resolve(strict=True)
    except OSError as exc:
        raise CrossoverProvenanceError(
            f"cannot resolve build directory {build_dir}: {exc}"
        ) from exc
    candidates = {
        path.resolve(strict=True)
        for path in build.rglob("libggml-cuda.so*")
        if path.is_file()
    }
    if len(candidates) != 1:
        raise CrossoverProvenanceError(
            "expected exactly one resolved libggml-cuda.so artifact, got "
            f"{[str(path) for path in sorted(candidates)]}"
        )
    return next(iter(candidates))


def collect_crossover_provenance(
    *,
    pid: int,
    expected_executable: Path,
    build_dir: Path,
    expected_argv_path: Path,
) -> dict[str, Any]:
    if pid <= 0:
        raise CrossoverProvenanceError("pid must be positive")

    expected_exe = expected_executable.expanduser().resolve(strict=True)
    expected_cuda = _find_cuda_backend(build_dir)
    expected_argv = _load_argv(expected_argv_path)

    proc = Path("/proc") / str(pid)
    try:
        observed_exe = (proc / "exe").resolve(strict=True)
        observed_argv = parse_proc_cmdline((proc / "cmdline").read_bytes())
        maps = parse_proc_maps((proc / "maps").read_text(encoding="utf-8"))
    except OSError as exc:
        raise CrossoverProvenanceError(
            f"cannot inspect live process {pid}: {exc}"
        ) from exc

    mismatches: list[str] = []
    if observed_exe != expected_exe:
        mismatches.append(
            f"process executable: {observed_exe} != {expected_exe}"
        )
    if observed_argv != expected_argv:
        mismatches.append("process argv does not exactly match frozen argv")

    deleted = [
        row["path"]
        for row in maps
        if row.get("deleted")
        and Path(str(row["path"])).name.startswith("libggml-cuda.so")
    ]
    if deleted:
        mismatches.append(f"mapped CUDA backend is deleted: {deleted}")

    exact_cuda = []
    for row in maps:
        if row.get("deleted"):
            continue
        path = Path(str(row["path"]))
        if not path.name.startswith("libggml-cuda.so"):
            continue
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            continue
        if resolved == expected_cuda:
            exact_cuda.append(row)

    if len(exact_cuda) != 1:
        mismatches.append(
            f"expected exactly one mapped build CUDA backend, got {len(exact_cuda)}"
        )
    elif int(exact_cuda[0]["inode"]) != expected_cuda.stat().st_ino:
        mismatches.append(
            "mapped CUDA backend inode differs from pre-run artifact"
        )

    other_cuda = []
    for row in maps:
        path = Path(str(row["path"]))
        if not path.name.startswith("libggml-cuda.so") or row.get("deleted"):
            continue
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            continue
        if resolved != expected_cuda:
            other_cuda.append(str(resolved))
    if other_cuda:
        mismatches.append(
            f"unexpected additional ggml-cuda mappings: {sorted(set(other_cuda))}"
        )

    return {
        "schema": "tesy.expert_crossover_runtime_provenance.v1",
        "classification": "MEASURED_LOCAL_PROVENANCE",
        "status": "PASS" if not mismatches else "FAIL",
        "pid": pid,
        "executable": {
            "expected": str(expected_exe),
            "observed": str(observed_exe),
            "sha256": _sha256(expected_exe),
        },
        "argv": {
            "expected": expected_argv,
            "observed": observed_argv,
            "status": "PASS" if observed_argv == expected_argv else "FAIL",
        },
        "ggml_cuda": {
            "path": str(expected_cuda),
            "inode": expected_cuda.stat().st_ino,
            "sha256": _sha256(expected_cuda),
            "mapped_matches": exact_cuda,
        },
        "mismatches": mismatches,
        "claim_boundary": (
            "PASS binds the live microbenchmark process to the expected executable, "
            "exact argv and the single libggml-cuda artifact built in the selected "
            "build directory. It does not establish numerical correctness, timing "
            "quality or physical PCIe traffic."
        ),
    }


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

    payload = collect_crossover_provenance(
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
