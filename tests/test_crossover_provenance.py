from pathlib import Path

import pytest

from tesy.crossover_provenance import (
    CrossoverProvenanceError,
    _find_cuda_backend,
)


def test_find_cuda_backend_deduplicates_symlink_aliases(tmp_path: Path):
    target = tmp_path / "libggml-cuda.so.0"
    target.write_bytes(b"cuda")
    alias = tmp_path / "libggml-cuda.so"
    alias.symlink_to(target.name)

    assert _find_cuda_backend(tmp_path) == target.resolve()


def test_find_cuda_backend_rejects_multiple_distinct_artifacts(tmp_path: Path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "libggml-cuda.so").write_bytes(b"a")
    (tmp_path / "b" / "libggml-cuda.so").write_bytes(b"b")

    with pytest.raises(
        CrossoverProvenanceError,
        match="expected exactly one resolved libggml-cuda",
    ):
        _find_cuda_backend(tmp_path)
