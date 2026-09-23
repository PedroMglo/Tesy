import json

import pytest

import tesy.build_provenance as build_provenance
from tesy.build_provenance import (
    BuildProvenanceError,
    collect_provenance,
    load_reference,
    parse_cmake_cache,
    sha256_file,
    validate_cache,
)


def _cache_text() -> str:
    return """CMAKE_BUILD_TYPE:STRING=Release
CMAKE_C_COMPILER:FILEPATH=/usr/bin/gcc-15
CMAKE_CXX_COMPILER:FILEPATH=/usr/bin/g++-15
CMAKE_CUDA_ARCHITECTURES:STRING=89
CMAKE_CUDA_COMPILER:FILEPATH=/usr/local/cuda/bin/nvcc
GGML_CUDA:BOOL=ON
"""


def _reference() -> dict:
    return {
        "schema": "tesy.reference_llama_toolchain.v1",
        "backend_id": "llama-cpp-stock",
        "llama_cpp_commit": "4e416ee7308dd6b581796f1a6241276cd5982691",
        "build_type": "Release",
        "ggml_cuda": "ON",
        "cuda_architectures": ["89"],
        "c_compiler": "/usr/bin/gcc-15",
        "cxx_compiler": "/usr/bin/g++-15",
        "cuda_compiler": "/usr/local/cuda/bin/nvcc",
        "c_compiler_version": "15.3.1",
        "cxx_compiler_version": "15.3.1",
        "cuda_compiler_version_contains": "V13.3.73",
        "cmake_version": "4.3.0",
        "llama_server_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "ggml_cuda_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    }


def test_parse_cmake_cache_and_validate_reference_match():
    cache = parse_cmake_cache(_cache_text())
    assert validate_cache(cache, _reference()) == []


def test_validate_cache_rejects_cuda_architecture_drift():
    cache = parse_cmake_cache(
        _cache_text().replace(
            "CMAKE_CUDA_ARCHITECTURES:STRING=89",
            "CMAKE_CUDA_ARCHITECTURES:STRING=89;120",
        )
    )
    assert validate_cache(cache, _reference()) == [
        "CMAKE_CUDA_ARCHITECTURES: ['89', '120'] != ['89']"
    ]


def test_parse_cmake_cache_rejects_missing_required_key():
    with pytest.raises(BuildProvenanceError, match="CMake cache missing required keys"):
        parse_cmake_cache(
            _cache_text().replace("GGML_CUDA:BOOL=ON\n", "")
        )


def test_load_reference_accepts_exact_lock(tmp_path):
    payload = _reference()
    path = tmp_path / "toolchain.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert load_reference(path) == payload


def test_load_reference_rejects_extra_fields(tmp_path):
    payload = _reference()
    payload["unexpected"] = True
    path = tmp_path / "toolchain.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BuildProvenanceError, match="unexpected toolchain lock fields"):
        load_reference(path)


def test_collect_provenance_passes_for_locked_fake_build(tmp_path, monkeypatch):
    build = tmp_path / "build"
    bin_dir = build / "bin"
    bin_dir.mkdir(parents=True)

    server = bin_dir / "llama-server"
    fit_tool = bin_dir / "llama-fit-params"
    cuda_backend = bin_dir / "libggml-cuda.so"
    c_compiler = tmp_path / "gcc-15"
    cxx_compiler = tmp_path / "g++-15"
    cuda_compiler = tmp_path / "nvcc"

    for path, content in (
        (server, "server"),
        (fit_tool, "fit"),
        (cuda_backend, "cuda"),
        (c_compiler, "gcc"),
        (cxx_compiler, "g++"),
        (cuda_compiler, "nvcc"),
    ):
        path.write_text(content, encoding="utf-8")

    cache = (
        "CMAKE_BUILD_TYPE:STRING=Release\n"
        f"CMAKE_C_COMPILER:FILEPATH={c_compiler}\n"
        f"CMAKE_CXX_COMPILER:FILEPATH={cxx_compiler}\n"
        "CMAKE_CUDA_ARCHITECTURES:STRING=89\n"
        f"CMAKE_CUDA_COMPILER:FILEPATH={cuda_compiler}\n"
        "GGML_CUDA:BOOL=ON\n"
    )
    (build / "CMakeCache.txt").write_text(cache, encoding="utf-8")

    reference = _reference()
    reference["c_compiler"] = str(c_compiler)
    reference["cxx_compiler"] = str(cxx_compiler)
    reference["cuda_compiler"] = str(cuda_compiler)
    reference["llama_server_sha256"] = sha256_file(server)
    reference["ggml_cuda_sha256"] = sha256_file(cuda_backend)
    reference_path = tmp_path / "reference.json"
    reference_path.write_text(json.dumps(reference), encoding="utf-8")

    def fake_run(command, *, timeout_s=20.0):
        del timeout_s
        executable = command[0]
        if executable == str(c_compiler):
            stdout = "15.3.1"
        elif executable == str(cxx_compiler):
            stdout = "15.3.1"
        elif executable == str(cuda_compiler):
            stdout = "Cuda compilation tools, release 13.3, V13.3.73"
        elif executable == "cmake":
            stdout = "cmake version 4.3.0"
        elif executable in {str(server), str(fit_tool)}:
            stdout = "Available devices:\n  CUDA0: Fake CUDA"
        elif executable == "ldd":
            stdout = "linux-vdso.so.1"
        else:
            raise AssertionError(f"unexpected command: {command}")
        return {
            "status": "OK",
            "returncode": 0,
            "stdout": stdout,
            "stderr": "",
            "command": command,
        }

    monkeypatch.setattr(build_provenance, "_run", fake_run)

    payload = collect_provenance(
        build_dir=build,
        server=server,
        fit_tool=fit_tool,
        reference_path=reference_path,
    )

    assert payload["status"] == "PASS"
    assert payload["mismatches"] == []
    assert payload["binaries"]["llama_server"]["sha256"] == sha256_file(server)
    assert payload["binaries"]["ggml_cuda"]["sha256"] == sha256_file(cuda_backend)
