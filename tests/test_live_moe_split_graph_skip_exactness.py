"""Model-free fixtures, mutations and fail-closed summary gate."""

import json
import shutil
import struct
from pathlib import Path

import pytest

from tesy.live_moe_split_graph_skip_exactness import (
    ARMS,
    BUILD_SCHEMA,
    INVENTORY_SCHEMA,
    MODEL_SHA,
    PIN,
    PROMPT_SHA,
    RAW_SCHEMA,
    SplitGraphValidationError,
    validate,
)


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture(scope="module")
def fixture_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("split-graph")
    _write_json(root / "build-provenance.json", {
        "schema": BUILD_SCHEMA,
        "status": "PASS",
        "upstream_llama_head": PIN,
        "stock_llama_head": PIN,
        "model_sha256": MODEL_SHA,
        "model_size_bytes": 12109564352,
        "prompt_sha256": PROMPT_SHA,
        "patch_sha256": "a" * 64,
        "patched_context_cpp_sha256": "b" * 64,
        "patched_context_h_sha256": "e" * 64,
        "stock_llama_tree": "f" * 40,
        "stock_binary_sha256": "c" * 64,
        "patched_binary_sha256": "d" * 64,
        "stock_libllama_sha256": "1" * 64,
        "patched_libllama_sha256": "2" * 64,
        "stock_binary_path": "/stock/tool",
        "patched_binary_path": "/patched/tool",
        "compiler_c": "/usr/bin/gcc-15",
        "compiler_cxx": "/usr/bin/g++-15",
        "cuda_compiler": "/usr/local/cuda/bin/nvcc",
        "cuda_architectures": "89",
    })
    logits_a = [0.0] * 201088
    logits_b = [0.0] * 201088
    logits_a[1309] = 1.0
    logits_b[316] = 1.0
    vectors = {
        "logits-a.f32": struct.pack("<201088f", *logits_a),
        "logits-b.f32": struct.pack("<201088f", *logits_b),
        "ffn-reference.f32": struct.pack("<2880f", *([1.0] * 2880)),
        "ffn-candidate.f32": struct.pack("<2880f", *([1.0] * 2880)),
    }
    for arm in ARMS:
        folder = root / arm
        folder.mkdir()
        split = arm not in ("stock", "null")
        skip = split and arm != "segmented"
        for name, payload in vectors.items():
            if split or name.startswith("logits"):
                (folder / name).write_bytes(payload)
        raw = {
            "schema": RAW_SCHEMA,
            "arm": arm,
            "layer": 0,
            "ngl": 0,
            "threads": 12,
            "first_token": 2167,
            "second_token": 1309,
            "third_token": 316,
            "gpu_hits": {"h2": 2, "h3": 3}.get(arm, 0),
            "committed_decode_return_code": 0,
            "continuation_decode_return_code": 0,
            "stock_capture_rollback": split,
            "handoff_capture_rollback": split,
            "ffn_bitwise": split,
            "prefix_compute_count": int(split),
            "middle_compute_count": int(arm == "segmented"),
            "suffix_compute_count": int(split),
            "injected_output_count": int(skip),
            "injected_bytes_verified": skip,
            "inventory_file": "inventory.json" if split else None,
            "ffn_reference_file": "ffn-reference.f32" if split else None,
            "ffn_candidate_file": "ffn-candidate.f32" if split else None,
            "logits_a_file": "logits-a.f32",
            "logits_b_file": "logits-b.f32",
            "selected_experts": [1, 13, 17, 21] if split else [],
            "routing_weights": [0.25] * 4 if split else [],
        }
        _write_json(folder / "raw.json", raw)
        _write_json(folder / "runtime-provenance.json", {"status": "PASS"})
        _write_json(folder / "resource-summary.json", {
            "status": "PASS", "gpu_failed_samples": 0,
            "peak_process_swap_bytes": 0,
        })
        if split:
            _write_json(folder / "inventory.json", {
                "schema": INVENTORY_SCHEMA,
                "total_nodes": 7,
                "activation_idx": 0,
                "topk_idx": 1,
                "weights_idx": 2,
                "moe_out_idx": 5,
                "prefix": [0, 3],
                "middle": [3, 6],
                "suffix": [6, 7],
                "all_nodes_cpu": True,
                "middle_contiguous": True,
                "downstream_depends_on_moe_out": True,
                "mul_mat_id_count": 1,
                "prefix_compute_count": 1,
                "middle_compute_count": int(arm == "segmented"),
                "suffix_compute_count": 1,
                "injected_output_count": int(skip),
                "skipped_nodes": [
                    {"index": 3, "name": "expert", "op": "MUL_MAT_ID"},
                    {"index": 4, "name": "aggregate", "op": "ADD"},
                    {"index": 5, "name": "ffn_moe_out-0", "op": "ADD"},
                ],
                "downstream_first": {"name": "residual", "op": "ADD"},
                "node_backends": ["CPU"] * 7,
            })
    return root


def _copy(root: Path, tmp_path: Path) -> Path:
    destination = tmp_path / "campaign"
    shutil.copytree(root, destination)
    return destination


def test_valid_model_free_campaign(fixture_root: Path) -> None:
    summary = validate(fixture_root)
    assert summary["decision"] == "LIVE_MOE_SPLIT_GRAPH_SKIP_EXACTNESS_GO"
    assert summary["arms"]["skip-stock"]["checkpoint_b"]["bitwise_equal"] is True


def test_reject_middle_execution_in_skip_arm(fixture_root: Path, tmp_path: Path) -> None:
    root = _copy(fixture_root, tmp_path)
    path = root / "h2" / "inventory.json"
    inventory = json.loads(path.read_text())
    inventory["middle_compute_count"] = 1
    _write_json(path, inventory)
    with pytest.raises(SplitGraphValidationError, match="view execution counts"):
        validate(root)


def test_reject_non_cpu_backend(fixture_root: Path, tmp_path: Path) -> None:
    root = _copy(fixture_root, tmp_path)
    path = root / "segmented" / "inventory.json"
    inventory = json.loads(path.read_text())
    inventory["node_backends"][4] = "CUDA0"
    _write_json(path, inventory)
    with pytest.raises(SplitGraphValidationError, match="backend assignments"):
        validate(root)


def test_reject_performance_field(fixture_root: Path, tmp_path: Path) -> None:
    root = _copy(fixture_root, tmp_path)
    path = root / "stock" / "raw.json"
    raw = json.loads(path.read_text())
    raw["median_ms"] = 1.0
    _write_json(path, raw)
    with pytest.raises(SplitGraphValidationError, match="performance field"):
        validate(root)


def test_reject_nonfinite_logits(fixture_root: Path, tmp_path: Path) -> None:
    root = _copy(fixture_root, tmp_path)
    path = root / "h3" / "logits-b.f32"
    with path.open("r+b") as handle:
        handle.seek(316 * 4)
        handle.write(struct.pack("<f", float("nan")))
    with pytest.raises(SplitGraphValidationError, match="non-finite F32"):
        validate(root)
