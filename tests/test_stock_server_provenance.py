from pathlib import Path

import pytest

from tesy import stock_server_provenance as provenance


def test_stock_server_provenance_waits_for_exact_mapped_backend(monkeypatch):
    observed = iter([
        {"status": "FAIL", "mismatches": ["backend not mapped yet"]},
        {"status": "PASS", "mismatches": []},
    ])
    monkeypatch.setattr(provenance, "collect_crossover_provenance", lambda **_: next(observed))
    monkeypatch.setattr(provenance.time, "sleep", lambda _: None)
    result = provenance.collect_stock_server_provenance(
        pid=1,
        expected_executable=Path("server"),
        build_dir=Path("build"),
        expected_argv_path=Path("argv.json"),
        attempts=2,
    )
    assert result["schema"] == "tesy.full_model_stock_server_runtime_provenance.v1"
    assert result["status"] == "PASS"


def test_stock_server_provenance_fails_closed(monkeypatch):
    monkeypatch.setattr(
        provenance,
        "collect_crossover_provenance",
        lambda **_: {"status": "FAIL", "mismatches": ["wrong CUDA backend"]},
    )
    monkeypatch.setattr(provenance.time, "sleep", lambda _: None)
    with pytest.raises(ValueError, match="wrong CUDA backend"):
        provenance.collect_stock_server_provenance(
            pid=1,
            expected_executable=Path("server"),
            build_dir=Path("build"),
            expected_argv_path=Path("argv.json"),
            attempts=1,
        )
