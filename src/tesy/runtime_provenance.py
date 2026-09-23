from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class RuntimeProvenanceError(ValueError):
    pass


_INTERESTING_PREFIXES = (
    "libggml",
    "libcuda.so",
    "libcudart.so",
    "libcublas",
    "libnvJitLink",
    "libnvrtc",
)


def parse_proc_maps(text: str) -> list[dict[str, Any]]:
    selected: dict[tuple[str, int], dict[str, Any]] = {}
    for raw in text.splitlines():
        parts = raw.split(maxsplit=5)
        if len(parts) != 6:
            continue
        pathname = parts[5]
        if not pathname.startswith("/"):
            continue
        deleted = pathname.endswith(" (deleted)")
        clean = pathname[: -len(" (deleted)")] if deleted else pathname
        name = Path(clean).name
        if not name.startswith(_INTERESTING_PREFIXES):
            continue
        try:
            inode = int(parts[4])
        except ValueError as exc:
            raise RuntimeProvenanceError(
                f"invalid /proc maps inode: {parts[4]!r}"
            ) from exc
        entry = {
            "path": clean,
            "inode": inode,
            "device": parts[3],
            "deleted": deleted,
        }
        selected[(clean, inode)] = entry
    return sorted(selected.values(), key=lambda row: (row["path"], row["inode"]))


def validate_runtime_identity(
    *,
    executable: Path,
    libraries: list[dict[str, Any]],
    build_provenance: dict[str, Any],
) -> list[str]:
    if build_provenance.get("schema") != "tesy.llama_build_provenance.v1":
        raise RuntimeProvenanceError("unsupported build provenance schema")
    if build_provenance.get("status") != "PASS":
        raise RuntimeProvenanceError("build provenance must PASS before runtime validation")

    binaries = build_provenance.get("binaries")
    if not isinstance(binaries, dict):
        raise RuntimeProvenanceError("build provenance binaries must be an object")

    server = binaries.get("llama_server")
    cuda = binaries.get("ggml_cuda")
    if not isinstance(server, dict) or not isinstance(cuda, dict):
        raise RuntimeProvenanceError("build provenance missing server or ggml_cuda")

    expected_server = Path(str(server.get("path"))).resolve(strict=True)
    expected_cuda = Path(str(cuda.get("path"))).resolve(strict=True)
    try:
        expected_cuda_inode = int(cuda["inode"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeProvenanceError("build provenance missing ggml_cuda inode") from exc

    observed_executable = executable.resolve(strict=True)
    mismatches: list[str] = []
    if observed_executable != expected_server:
        mismatches.append(
            f"process executable: {observed_executable} != {expected_server}"
        )

    deleted = [row["path"] for row in libraries if row.get("deleted")]
    if deleted:
        mismatches.append(f"selected mapped libraries are deleted: {deleted}")

    matches = []
    for row in libraries:
        if row.get("deleted"):
            continue
        try:
            resolved = Path(str(row["path"])).resolve(strict=True)
        except OSError:
            continue
        if resolved == expected_cuda:
            matches.append(row)

    if len(matches) != 1:
        mismatches.append(
            f"expected exactly one mapped ggml-cuda identity, got {len(matches)}"
        )
    elif int(matches[0]["inode"]) != expected_cuda_inode:
        mismatches.append(
            f"mapped ggml-cuda inode: {matches[0]['inode']} != {expected_cuda_inode}"
        )
    return mismatches


def collect_runtime_provenance(
    *, pid: int, build_provenance_path: Path
) -> dict[str, Any]:
    if pid <= 0:
        raise RuntimeProvenanceError("pid must be positive")
    proc = Path("/proc") / str(pid)
    try:
        executable = (proc / "exe").resolve(strict=True)
        maps_text = (proc / "maps").read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeProvenanceError(f"cannot inspect process {pid}: {exc}") from exc

    try:
        build_provenance = json.loads(
            build_provenance_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeProvenanceError(
            f"cannot read build provenance {build_provenance_path}: {exc}"
        ) from exc

    libraries = parse_proc_maps(maps_text)
    mismatches = validate_runtime_identity(
        executable=executable,
        libraries=libraries,
        build_provenance=build_provenance,
    )

    return {
        "schema": "tesy.runtime_backend_provenance.v1",
        "classification": "MEASURED_LOCAL_PROVENANCE",
        "status": "PASS" if not mismatches else "FAIL",
        "pid": pid,
        "executable": str(executable),
        "selected_mapped_libraries": libraries,
        "mismatches": mismatches,
        "claim_boundary": (
            "PASS verifies the live process executable and that the pre-hashed "
            "ggml-cuda artifact is the CUDA backend actually mapped by this server. "
            "It does not prove model correctness or performance."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--build-provenance", required=True, type=Path)
    args = parser.parse_args()

    payload = collect_runtime_provenance(
        pid=args.pid,
        build_provenance_path=args.build_provenance,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
