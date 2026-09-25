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
    write_json(
        root / "build-provenance.json",
        {
            "schema": "tesy.stock_prefix_build_provenance.v1",
            "status": "PASS",
            "llama_head": "4e416ee7308dd6b581796f1a6241276cd5982691",
            "model_sha256": "52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4",
            "model_size_bytes": 12109564352,
        },
    )
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
                write_json(
                    run / "raw.json",
                    {
                        "schema": "tesy.stock_prefix_logits_raw.v1",
                        "n_gpu_layers": ngl,
                        "n_ctx": 4096,
                        "n_threads": 12,
                        "n_vocab": 64,
                        "n_batch": 2,
                        "n_ubatch": 2,
                        "tokenization": {"add_special": True, "parse_special": True},
                        "prompt_tokens": [1, 2],
                        "common_token": 32,
                        "greedy_p": 32,
                        "greedy_d": 3,
                    },
                )
                write_json(
                    run / "runtime-provenance.json",
                    {
                        "schema": "tesy.mixed_residency_runtime_provenance.v1",
                        "status": "PASS",
                    },
                )
                write_json(
                    run / "resource-summary.json",
                    {
                        "schema": "tesy.stock_prefix_resource_summary.v1",
                        "status": "PASS",
                        "valid_samples": 2,
                        "peak_process_swap_bytes": 0,
                        "gpu_failed_samples": 0,
                        "terminal_samples_excluded": 1,
                    },
                )
                valid_row = {
                    "process": {"VmRSS_bytes": 1000, "VmSwap_bytes": 0},
                    "gpu": {"status": "OK", "temperature_c": 40.0, "power_w": 10.0},
                }
                terminal_row = {"process": {}, "gpu": {"status": "OK"}}
                (run / "resources.jsonl").write_text(
                    "\n".join(json.dumps(x) for x in (valid_row, valid_row, terminal_row)) + "\n"
                )
                (run / "stderr.txt").write_text(
                    "\n".join(
                        f"load_tensors: layer {i:3d} assigned to device "
                        f"{'CUDA0' if ngl == 12 and i >= 13 else 'CPU'}, is_swa = 0"
                        for i in range(25)
                    )
                    + "\n"
                )
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


def test_b_detects_stock_contrast_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_resource_trace_rejects_nonterminal_gap(tmp_path: Path) -> None:
    path = tmp_path / "resources.jsonl"
    valid = {
        "process": {"VmRSS_bytes": 1, "VmSwap_bytes": 0},
        "gpu": {"status": "OK", "temperature_c": 40.0, "power_w": 1.0},
    }
    missing = {"process": {}, "gpu": {"status": "OK"}}
    path.write_text("\n".join(json.dumps(x) for x in (valid, missing, valid)) + "\n")
    with pytest.raises(ab.CharacterizationError, match="nonterminal"):
        ab.validate_resource_trace(path)


def test_json_parser_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text('{"schema":"example.v1","schema":"example.v1"}')
    with pytest.raises(ab.CharacterizationError, match="duplicate JSON key"):
        ab.read_json(path, "example.v1")


def test_a_rechecks_diagonals_and_decomposition(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    sidecars = repo / ab.N2_DIR
    stock = ab.read_f32(sidecars / "layer2-stock-ffn_moe_down.f32", ab.EMBD * 4)
    mixed = ab.read_f32(sidecars / "layer2-mixed-ffn_moe_down.f32", ab.EMBD * 4)
    vectors = {
        "C_xC": stock.reshape(4, ab.EMBD)[1].copy(),
        "C_xG": stock.reshape(4, ab.EMBD)[1].copy(),
        "G_xC": mixed.reshape(4, ab.EMBD)[1].copy(),
        "G_xG": mixed.reshape(4, ab.EMBD)[1].copy(),
    }
    for arm, values in vectors.items():
        for repeat in (1, 2):
            values.tofile(tmp_path / f"{arm}-r{repeat}.f32")
    write_json(
        tmp_path / "raw.json",
        {
            "schema": "tesy.numerical_characterization_a_raw.v1",
        },
    )
    write_json(
        tmp_path / "down-matrix-raw.json",
        {
            "schema": "tesy.numerical_down_matrix_raw.v1",
            "route": [4, 0, 31, 17],
            "slot": 1,
            "expert": 0,
            "cpu_ids": [4, 0, 31, 17],
            "gpu_local_ids": [0],
            "cpu_slots": 4,
            "gpu_slots": 1,
            "replay_nodes": 1,
            "repetitions": 2,
            "diagonal_bitwise": {"C_xC": True, "G_xG": True},
            "repeat_bitwise": {arm: True for arm in vectors},
        },
    )
    write_json(
        tmp_path / "resource-summary.json",
        {
            "schema": "tesy.vertical_live_resource_summary.v1",
            "status": "PASS",
            "valid_samples": 2,
        },
    )
    sample = {
        "process": {"VmRSS_bytes": 1, "VmSwap_bytes": 0},
        "gpu": {"status": "OK", "temperature_c": 40.0, "power_w": 1.0},
    }
    (tmp_path / "resources.jsonl").write_text(json.dumps(sample) + "\n" + json.dumps(sample) + "\n")
    result = ab.analyze_a(repo, tmp_path)
    assert result["diagnostic_result"] == "COMPLETE"
    assert (
        result["decomposition_float64"]["gpu_input_plus_backend_stock_input_max_abs_residual"]
        == 0.0
    )
    vectors["G_xG"].tofile(tmp_path / "C_xC-r1.f32")
    with pytest.raises(ab.CharacterizationError, match="repeat flag"):
        ab.analyze_a(repo, tmp_path)
