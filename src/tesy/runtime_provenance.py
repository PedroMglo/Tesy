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


def parse_proc_cmdline(data: bytes) -> list[str]:
    if not data:
        raise RuntimeProvenanceError("empty /proc cmdline")
    raw_items = data.split(b"\0")
    if raw_items and raw_items[-1] == b"":
        raw_items.pop()
    if not raw_items:
        raise RuntimeProvenanceError("empty /proc cmdline")
    result: list[str] = []
    for raw in raw_items:
        if not raw:
            raise RuntimeProvenanceError("empty argv element in /proc cmdline")
        try:
            value = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise RuntimeProvenanceError("/proc cmdline is not valid UTF-8") from exc
        result.append(value)
    return result


def _load_expected_argv(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeProvenanceError(
            f"cannot read expected argv {path}: {exc}"
        ) from exc
    if not isinstance(payload, list) or not payload:
        raise RuntimeProvenanceError("expected argv must be a non-empty JSON list")
    result: list[str] = []
    for value in payload:
        if not isinstance(value, str) or not value:
            raise RuntimeProvenanceError(
                "expected argv must contain non-empty strings only"
            )
        result.append(value)
    return result


def validate_runtime_identity(
    *,
    executable: Path,
    libraries: list[dict[str, Any]],
    build_provenance: dict[str, Any],
    observed_argv: list[str] | None = None,
    expected_argv: list[str] | None = None,
) -> list[str]:
    if build_provenance.get("schema") != "tesy.llama_build_provenance.v1":
        raise RuntimeProvenanceError("unsupported build provenance schema")
    if build_provenance.get("status") != "PASS":
        raise RuntimeProvenanceError(
            "build provenance must PASS before runtime validation"
        )

    binaries = build_provenance.get("binaries")
    if not isinstance(binaries, dict):
        raise RuntimeProvenanceError("build provenance binaries must be an object")

    server = binaries.get("llama_server")
    cuda = binaries.get("ggml_cuda")
    if not isinstance(server, dict) or not isinstance(cuda, dict):
        raise RuntimeProvenanceError(
            "build provenance missing server or ggml_cuda"
        )

    expected_server = Path(str(server.get("path"))).resolve(strict=True)
    expected_cuda = Path(str(cuda.get("path"))).resolve(strict=True)
    try:
        expected_cuda_inode = int(cuda["inode"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeProvenanceError(
            "build provenance missing ggml_cuda inode"
        ) from exc

    observed_executable = executable.resolve(strict=True)
    mismatches: list[str] = []
    if observed_executable != expected_server:
        mismatches.append(
            f"process executable: {observed_executable} != {expected_server}"
        )

    if (observed_argv is None) != (expected_argv is None):
        raise RuntimeProvenanceError(
            "observed_argv and expected_argv must be supplied together"
        )
    if observed_argv is not None and expected_argv is not None:
        if observed_argv != expected_argv:
            mismatches.append(
                "process argv does not exactly match frozen expected argv"
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
    *,
    pid: int,
    build_provenance_path: Path,
    expected_argv_path: Path | None = None,
) -> dict[str, Any]:
    if pid <= 0:
        raise RuntimeProvenanceError("pid must be positive")
    proc = Path("/proc") / str(pid)
    try:
        executable = (proc / "exe").resolve(strict=True)
        maps_text = (proc / "maps").read_text(encoding="utf-8")
        observed_argv = parse_proc_cmdline((proc / "cmdline").read_bytes())
    except OSError as exc:
        raise RuntimeProvenanceError(
            f"cannot inspect process {pid}: {exc}"
        ) from exc

    try:
        build_provenance = json.loads(
            build_provenance_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeProvenanceError(
            f"cannot read build provenance {build_provenance_path}: {exc}"
        ) from exc

    expected_argv = (
        _load_expected_argv(expected_argv_path)
        if expected_argv_path is not None
        else None
    )
    libraries = parse_proc_maps(maps_text)
    mismatches = validate_runtime_identity(
        executable=executable,
        libraries=libraries,
        build_provenance=build_provenance,
        observed_argv=observed_argv if expected_argv is not None else None,
        expected_argv=expected_argv,
    )

    return {
        "schema": "tesy.runtime_backend_provenance.v1",
        "classification": "MEASURED_LOCAL_PROVENANCE",
        "status": "PASS" if not mismatches else "FAIL",
        "pid": pid,
        "executable": str(executable),
        "argv": {
            "observed": observed_argv,
            "expected": expected_argv,
            "status": (
                "NOT_CHECKED"
                if expected_argv is None
                else "PASS"
                if observed_argv == expected_argv
                else "FAIL"
            ),
        },
        "selected_mapped_libraries": libraries,
        "mismatches": mismatches,
        "claim_boundary": (
            "PASS verifies the live process executable, optional exact argv "
            "identity, and that the pre-hashed ggml-cuda artifact is the CUDA "
            "backend actually mapped by this server. It does not prove model "
            "correctness or performance."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--build-provenance", required=True, type=Path)
    parser.add_argument("--expected-argv", type=Path)
    args = parser.parse_args()

    payload = collect_runtime_provenance(
        pid=args.pid,
        build_provenance_path=args.build_provenance,
        expected_argv_path=args.expected_argv,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
