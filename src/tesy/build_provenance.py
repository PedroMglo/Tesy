from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any


class BuildProvenanceError(ValueError):
    pass


_REQUIRED_CACHE_KEYS = {
    "CMAKE_BUILD_TYPE",
    "CMAKE_C_COMPILER",
    "CMAKE_CXX_COMPILER",
    "CMAKE_CUDA_ARCHITECTURES",
    "CMAKE_CUDA_COMPILER",
    "GGML_CUDA",
}

_REFERENCE_KEYS = {
    "schema",
    "backend_id",
    "llama_cpp_commit",
    "build_type",
    "ggml_cuda",
    "cuda_architectures",
    "c_compiler",
    "cxx_compiler",
    "cuda_compiler",
    "c_compiler_version",
    "cxx_compiler_version",
    "cuda_compiler_version_contains",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def parse_cmake_cache(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "//")) or "=" not in line:
            continue
        key_type, value = line.split("=", 1)
        if ":" not in key_type:
            continue
        key, _type = key_type.split(":", 1)
        if not key:
            raise BuildProvenanceError("empty CMake cache key")
        if key in parsed:
            raise BuildProvenanceError(f"duplicate CMake cache key: {key}")
        parsed[key] = value

    missing = sorted(_REQUIRED_CACHE_KEYS - parsed.keys())
    if missing:
        raise BuildProvenanceError(
            f"CMake cache missing required keys: {', '.join(missing)}"
        )
    return parsed


def load_reference(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildProvenanceError(f"cannot read toolchain lock {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise BuildProvenanceError("toolchain lock must be an object")
    extras = sorted(set(payload) - _REFERENCE_KEYS)
    missing = sorted(_REFERENCE_KEYS - set(payload))
    if extras:
        raise BuildProvenanceError(f"unexpected toolchain lock fields: {extras}")
    if missing:
        raise BuildProvenanceError(f"missing toolchain lock fields: {missing}")
    if payload["schema"] != "tesy.reference_llama_toolchain.v1":
        raise BuildProvenanceError("unsupported toolchain lock schema")
    if payload["backend_id"] != "llama-cpp-stock":
        raise BuildProvenanceError("unsupported backend_id in toolchain lock")
    arch = payload["cuda_architectures"]
    if not isinstance(arch, list) or not arch or not all(
        isinstance(item, str) and item for item in arch
    ):
        raise BuildProvenanceError("cuda_architectures must be a non-empty string list")
    for key in (
        "llama_cpp_commit",
        "build_type",
        "ggml_cuda",
        "c_compiler",
        "cxx_compiler",
        "cuda_compiler",
        "c_compiler_version",
        "cxx_compiler_version",
        "cuda_compiler_version_contains",
    ):
        if not isinstance(payload[key], str) or not payload[key]:
            raise BuildProvenanceError(f"{key} must be a non-empty string")
    return payload


def validate_cache(cache: dict[str, str], reference: dict[str, Any]) -> list[str]:
    expected = {
        "CMAKE_BUILD_TYPE": reference["build_type"],
        "GGML_CUDA": reference["ggml_cuda"],
        "CMAKE_C_COMPILER": reference["c_compiler"],
        "CMAKE_CXX_COMPILER": reference["cxx_compiler"],
        "CMAKE_CUDA_COMPILER": reference["cuda_compiler"],
    }
    mismatches = [
        f"{key}: {cache.get(key)!r} != {value!r}"
        for key, value in expected.items()
        if cache.get(key) != value
    ]

    observed_arch = [item for item in cache["CMAKE_CUDA_ARCHITECTURES"].split(";") if item]
    if observed_arch != reference["cuda_architectures"]:
        mismatches.append(
            "CMAKE_CUDA_ARCHITECTURES: "
            f"{observed_arch!r} != {reference['cuda_architectures']!r}"
        )
    return mismatches


def _run(command: list[str], *, timeout_s: float = 20.0) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "ERROR",
            "command": command,
            "error": str(exc),
        }
    return {
        "status": "OK" if completed.returncode == 0 else "ERROR",
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "command": command,
    }


def _resolved_regular(path: Path, *, label: str) -> Path:
    try:
        resolved = path.expanduser().resolve(strict=True)
    except OSError as exc:
        raise BuildProvenanceError(f"cannot resolve {label} {path}: {exc}") from exc
    if not resolved.is_file():
        raise BuildProvenanceError(f"{label} must be a regular file: {resolved}")
    return resolved


def _require_within(path: Path, root: Path, *, label: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise BuildProvenanceError(
            f"{label} must come from build directory {root}: {path}"
        ) from exc


def _compiler_probe(path: Path, version_args: list[str]) -> dict[str, Any]:
    result = _run([str(path), *version_args])
    result["path"] = str(path)
    result["sha256"] = sha256_file(path)
    return result


def _find_cuda_backend(build_dir: Path) -> Path:
    resolved = {
        candidate.resolve(strict=True)
        for candidate in build_dir.rglob("libggml-cuda.so*")
        if candidate.is_file()
    }
    if len(resolved) != 1:
        raise BuildProvenanceError(
            "expected exactly one resolved libggml-cuda.so artifact, "
            f"got {[str(path) for path in sorted(resolved)]}"
        )
    return next(iter(resolved))


def collect_provenance(
    *,
    build_dir: Path,
    server: Path,
    fit_tool: Path,
    reference_path: Path,
) -> dict[str, Any]:
    build = build_dir.expanduser().resolve(strict=True)
    if not build.is_dir():
        raise BuildProvenanceError(f"build_dir is not a directory: {build}")

    cache_path = _resolved_regular(build / "CMakeCache.txt", label="CMake cache")
    cache = parse_cmake_cache(cache_path.read_text(encoding="utf-8"))
    reference = load_reference(reference_path)

    server_path = _resolved_regular(server, label="llama-server")
    fit_path = _resolved_regular(fit_tool, label="llama-fit-params")
    _require_within(server_path, build, label="llama-server")
    _require_within(fit_path, build, label="llama-fit-params")

    cache_mismatches = validate_cache(cache, reference)

    c_path = _resolved_regular(Path(cache["CMAKE_C_COMPILER"]), label="C compiler")
    cxx_path = _resolved_regular(Path(cache["CMAKE_CXX_COMPILER"]), label="CXX compiler")
    cuda_path = _resolved_regular(
        Path(cache["CMAKE_CUDA_COMPILER"]), label="CUDA compiler"
    )

    c_probe = _compiler_probe(c_path, ["-dumpfullversion"])
    cxx_probe = _compiler_probe(cxx_path, ["-dumpfullversion"])
    cuda_probe = _compiler_probe(cuda_path, ["--version"])
    cmake_probe = _run(["cmake", "--version"])

    compiler_mismatches: list[str] = []
    if c_probe.get("stdout") != reference["c_compiler_version"]:
        compiler_mismatches.append(
            f"C compiler version: {c_probe.get('stdout')!r} "
            f"!= {reference['c_compiler_version']!r}"
        )
    if cxx_probe.get("stdout") != reference["cxx_compiler_version"]:
        compiler_mismatches.append(
            f"CXX compiler version: {cxx_probe.get('stdout')!r} "
            f"!= {reference['cxx_compiler_version']!r}"
        )
    cuda_version_text = "\n".join(
        [cuda_probe.get("stdout", ""), cuda_probe.get("stderr", "")]
    )
    if reference["cuda_compiler_version_contains"] not in cuda_version_text:
        compiler_mismatches.append(
            "CUDA compiler version output missing "
            f"{reference['cuda_compiler_version_contains']!r}"
        )

    cuda_backend = _find_cuda_backend(build)
    server_devices = _run([str(server_path), "--list-devices"])
    fit_devices = _run([str(fit_path), "--list-devices"])
    ldd_server = _run(["ldd", str(server_path)])
    ldd_fit = _run(["ldd", str(fit_path)])

    command_failures = [
        name
        for name, result in {
            "cmake": cmake_probe,
            "c_compiler": c_probe,
            "cxx_compiler": cxx_probe,
            "cuda_compiler": cuda_probe,
            "server_devices": server_devices,
            "fit_devices": fit_devices,
            "ldd_server": ldd_server,
            "ldd_fit": ldd_fit,
        }.items()
        if result.get("status") != "OK"
    ]

    device_mismatches: list[str] = []
    for name, result in {
        "server": server_devices,
        "fit_tool": fit_devices,
    }.items():
        text = "\n".join([result.get("stdout", ""), result.get("stderr", "")])
        if "CUDA0:" not in text:
            device_mismatches.append(f"{name} --list-devices missing CUDA0")

    mismatches = cache_mismatches + compiler_mismatches + device_mismatches
    if command_failures:
        mismatches.append(f"failed provenance commands: {command_failures}")

    return {
        "schema": "tesy.llama_build_provenance.v1",
        "classification": "MEASURED_LOCAL_PROVENANCE",
        "status": "PASS" if not mismatches else "FAIL",
        "reference": reference,
        "cmake_cache": {
            "path": str(cache_path),
            "sha256": sha256_file(cache_path),
            "selected": {key: cache[key] for key in sorted(_REQUIRED_CACHE_KEYS)},
        },
        "cmake": cmake_probe,
        "compilers": {
            "c": c_probe,
            "cxx": cxx_probe,
            "cuda": cuda_probe,
        },
        "binaries": {
            "llama_server": {
                "path": str(server_path),
                "bytes": server_path.stat().st_size,
                "sha256": sha256_file(server_path),
            },
            "llama_fit_params": {
                "path": str(fit_path),
                "bytes": fit_path.stat().st_size,
                "sha256": sha256_file(fit_path),
            },
            "ggml_cuda": {
                "path": str(cuda_backend),
                "bytes": cuda_backend.stat().st_size,
                "sha256": sha256_file(cuda_backend),
            },
        },
        "devices": {
            "llama_server": server_devices,
            "llama_fit_params": fit_devices,
        },
        "dynamic_dependencies": {
            "llama_server": ldd_server,
            "llama_fit_params": ldd_fit,
        },
        "mismatches": mismatches,
        "claim_boundary": (
            "PASS establishes the locked CMake/toolchain fields, exact binary and "
            "ggml-cuda hashes, runnable dependency resolution, and CUDA0 visibility "
            "for this local build. It is not model correctness or performance."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--server", required=True, type=Path)
    parser.add_argument("--fit-tool", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    args = parser.parse_args()

    payload = collect_provenance(
        build_dir=args.build_dir,
        server=args.server,
        fit_tool=args.fit_tool,
        reference_path=args.reference,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
