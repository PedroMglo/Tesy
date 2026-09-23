import json

import pytest

from tesy.build_provenance import (
    BuildProvenanceError,
    load_reference,
    parse_cmake_cache,
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
