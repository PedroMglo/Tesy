import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from tesy import numerical_characterization_ab as ab


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value) + "\n")


def test_f32_parser_rejects_truncation_and_nonfinite(tmp_path: Path) -> None:
    path = tmp_path / "vector.f32"
    np.array([1.0, 2.0], dtype="<f4").tofile(path)
    assert ab.read_f32(path, 2).tolist() == [1.0, 2.0]
    with pytest.raises(ab.CharacterizationError, match="truncated"):
        ab.read_f32(path, 3)
    np.array([1.0, np.nan], dtype="<f4").tofile(path)
    with pytest.raises(ab.CharacterizationError, match="non-finite"):
        ab.read_f32(path, 2)


def test_metrics_use_frozen_denominator_and_vector_arithmetic() -> None:
    reference = np.array([0.5, -0.25, 0.0], dtype="<f4")
    candidate = np.array([0.75, -0.25, 0.0], dtype="<f4")
    value = ab.metrics(reference, candidate)
    assert value["max_abs"] == 0.25
    assert value["max_abs_ref"] == 0.5
    assert value["relative_max"] == 0.25
    assert value["bitwise_equal"] is False
    assert ab.contract(value) == "FAIL"
    assert ab.metrics(reference, reference)["bitwise_equal"] is True


def fake_b_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(ab, "VOCAB", 64)
    root = tmp_path / "B"
    root.mkdir()
    write_json(root / "build-provenance.json", {
        "schema": "tesy.stock_prefix_build_provenance.v1", "status": "PASS",
        "llama_head": "4e416ee7308dd6b581796f1a6241276cd5982691",
    })
    p = np.zeros(64, dtype="<f4")
    p[32] = 2.0
    d = np.zeros(64, dtype="<f4")
    d[3] = 3.0
    monkeypatch.setattr(ab, "N1_STOCK_SHA", hashlib.sha256(d.tobytes()).hexdigest())
    for label in ("historical", "code"):
        for repeat in (1, 2):
            for ngl in (0, 12):
                run = root / f"{label}-r{repeat}-ngl{ngl}"
                run.mkdir()
                write_json(run / "raw.json", {
                    "schema": "tesy.stock_prefix_logits_raw.v1",
                    "n_gpu_layers": ngl, "n_ctx": 4096, "n_threads": 12,
                    "n_vocab": 64, "n_batch": 2, "n_ubatch": 2,
                    "tokenization": {"add_special": True, "parse_special": True},
                    "prompt_tokens": [1, 2], "common_token": 32,
                    "greedy_p": 32, "greedy_d": 3,
                })
                write_json(run / "runtime-provenance.json", {
                    "schema": "tesy.mixed_residency_runtime_provenance.v1", "status": "PASS",
                })
                write_json(run / "resource-summary.json", {
                    "schema": "tesy.stock_prefix_resource_summary.v1", "status": "PASS",
                    "valid_samples": 2, "peak_process_swap_bytes": 0,
                    "gpu_failed_samples": 0,
                })
                p.tofile(run / "P.f32")
                d.tofile(run / "D.f32")
    return root


def test_b_requires_same_prefix_and_recomputes_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = Path(__file__).resolve().parents[1]
    root = fake_b_root(tmp_path, monkeypatch)
    result = ab.analyze_b(repo, root)
    assert result["historical_b0_d_bitwise_n2"] is True
    assert result["repeatable_within_placement_bitwise"] is True
    assert result["comparison_under_existing_contract"] == "PASS_OBSERVED_CASES"
    path = root / "code-r2-ngl12/raw.json"
    raw = json.loads(path.read_text())
    raw["common_token"] = 33
    write_json(path, raw)
    with pytest.raises(ab.CharacterizationError, match="different prefixes"):
        ab.analyze_b(repo, root)


def test_b_detects_stock_contrast_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = Path(__file__).resolve().parents[1]
    root = fake_b_root(tmp_path, monkeypatch)
    for label in ("historical", "code"):
        for repeat in (1, 2):
            run = root / f"{label}-r{repeat}-ngl12/D.f32"
            values = ab.read_f32(run, 64).copy()
            values[3] = 3.1
            values.tofile(run)
    result = ab.analyze_b(repo, root)
    assert result["comparison_under_existing_contract"] == "NUMERICAL_CONTRACT_REVIEW_REQUIRED"
