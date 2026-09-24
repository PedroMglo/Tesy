"""Validação independente do gate CPU split-graph/stock-MoE skip."""

from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path
from typing import Any


class SplitGraphValidationError(ValueError):
    """Artefacto inválido ou gate de correctness falhado."""


RAW_SCHEMA = "tesy.live_moe_split_graph_skip_exactness_raw.v1"
INVENTORY_SCHEMA = "tesy.live_moe_split_graph_inventory.v1"
SUMMARY_SCHEMA = "tesy.live_moe_split_graph_skip_exactness_summary.v1"
BUILD_SCHEMA = "tesy.live_moe_split_graph_build_provenance.v1"
DECISION = "LIVE_MOE_SPLIT_GRAPH_SKIP_EXACTNESS_GO"
PIN = "4e416ee7308dd6b581796f1a6241276cd5982691"
MODEL_SHA = "52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4"
PROMPT_SHA = "431498aa6a73a4e817c5ef58ceabdac5b8336dd95e01a17903e75bc1d27d10c6"
ARMS = ("stock", "null", "segmented", "skip-stock", "h2", "h3")
FORBIDDEN = ("median_ms", "p95_ms", "samples_ms", "speedup", "tok_s", "tpot", "ttft")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SplitGraphValidationError(message)


def _reject_performance(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _require(not any(term in key.lower() for term in FORBIDDEN),
                     f"performance field forbidden: {key}")
            _reject_performance(child)
    elif isinstance(value, list):
        for child in value:
            _reject_performance(child)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path}: object required")
    _reject_performance(value)
    return value


def _floats(path: Path, count: int) -> tuple[bytes, list[float]]:
    payload = path.read_bytes()
    _require(len(payload) == count * 4, f"{path}: F32 byte count mismatch")
    values = [item[0] for item in struct.iter_unpack("<f", payload)]
    _require(all(math.isfinite(value) for value in values),
             f"{path}: non-finite F32")
    return payload, values


def _parity(reference: tuple[bytes, list[float]],
            candidate: tuple[bytes, list[float]]) -> dict[str, Any]:
    ref_bytes, ref = reference
    cand_bytes, cand = candidate
    _require(len(ref) == len(cand) and len(ref) > 0, "parity vector count mismatch")
    max_abs = max(abs(a - b) for a, b in zip(ref, cand, strict=True))
    max_ref = max(abs(a) for a in ref)
    relative = max_abs / max(1.0, max_ref)
    dot = math.fsum(a * b for a, b in zip(ref, cand, strict=True))
    norm_ref = math.fsum(a * a for a in ref)
    norm_cand = math.fsum(b * b for b in cand)
    cosine = dot / max(1e-30, math.sqrt(norm_ref * norm_cand))
    passed = all(math.isfinite(x) for x in (max_abs, max_ref, relative, cosine))
    passed = passed and relative <= 0.005 and cosine >= 0.9999
    return {
        "element_count": len(ref),
        "max_abs": max_abs,
        "max_abs_ref": max_ref,
        "relative_max": relative,
        "cosine": cosine,
        "bitwise_equal": ref_bytes == cand_bytes,
        "status": "PASS" if passed else "FAIL",
    }


def _inventory(root: Path, arm: str, raw: dict[str, Any]) -> dict[str, Any]:
    _require(raw.get("inventory_file") == "inventory.json",
             f"{arm}: inventory path mismatch")
    inventory = _json(root / arm / "inventory.json")
    _require(inventory.get("schema") == INVENTORY_SCHEMA,
             f"{arm}: inventory schema mismatch")
    n = inventory.get("total_nodes")
    a = inventory.get("activation_idx")
    t = inventory.get("topk_idx")
    w = inventory.get("weights_idx")
    m = inventory.get("moe_out_idx")
    _require(all(type(value) is int for value in (n, a, t, w, m))
             and 0 <= a < t < w < m < n - 1,
             f"{arm}: boundary indices invalid")
    _require(inventory.get("prefix") == [0, w + 1]
             and inventory.get("middle") == [w + 1, m + 1]
             and inventory.get("suffix") == [m + 1, n],
             f"{arm}: graph ranges invalid")
    _require(inventory.get("all_nodes_cpu") is True
             and inventory.get("middle_contiguous") is True
             and inventory.get("downstream_depends_on_moe_out") is True,
             f"{arm}: CPU/topology proof failed")
    assignments = inventory.get("node_backends")
    _require(isinstance(assignments, list) and len(assignments) == n
             and len(set(assignments)) == 1 and "CPU" in assignments[0].upper(),
             f"{arm}: backend assignments invalid")
    nodes = inventory.get("skipped_nodes")
    _require(isinstance(nodes, list) and len(nodes) == m - w,
             f"{arm}: skipped node count invalid")
    _require([row.get("index") for row in nodes] == list(range(w + 1, m + 1)),
             f"{arm}: skipped node indices invalid")
    _require(all(isinstance(row.get("name"), str) and row["name"]
                 and isinstance(row.get("op"), str) and row["op"]
                 for row in nodes), f"{arm}: skipped node metadata invalid")
    matmul_count = sum(row["op"] == "MUL_MAT_ID" for row in nodes)
    _require(matmul_count > 0 and inventory.get("mul_mat_id_count") == matmul_count,
             f"{arm}: expert compute inventory invalid")
    _require(nodes[-1]["name"] == "ffn_moe_out-0",
             f"{arm}: middle does not end at stock output")
    downstream = inventory.get("downstream_first")
    _require(isinstance(downstream, dict) and downstream.get("name")
             and downstream.get("op"), f"{arm}: downstream node invalid")
    expected = (1, 0 if arm != "segmented" else 1, 1,
                0 if arm == "segmented" else 1)
    counts = tuple(inventory.get(key) for key in (
        "prefix_compute_count", "middle_compute_count",
        "suffix_compute_count", "injected_output_count"))
    _require(counts == expected, f"{arm}: view execution counts invalid")
    _require(counts == tuple(raw.get(key) for key in (
        "prefix_compute_count", "middle_compute_count",
        "suffix_compute_count", "injected_output_count")),
        f"{arm}: inventory/raw execution counts diverge")
    return inventory


def validate(root: Path) -> dict[str, Any]:
    build = _json(root / "build-provenance.json")
    _require(build.get("schema") == BUILD_SCHEMA and build.get("status") == "PASS",
             "build provenance invalid")
    _require(build.get("upstream_llama_head") == PIN
             and build.get("stock_llama_head") == PIN
             and build.get("model_sha256") == MODEL_SHA
             and build.get("model_size_bytes") == 12109564352
             and build.get("prompt_sha256") == PROMPT_SHA,
             "pinned identity mismatch")
    for key in ("patch_sha256", "patched_context_cpp_sha256",
                "patched_context_h_sha256", "stock_llama_tree",
                "stock_binary_sha256",
                "patched_binary_sha256", "stock_binary_path", "patched_binary_path",
                "compiler_c", "compiler_cxx", "cuda_compiler", "cuda_architectures"):
        _require(isinstance(build.get(key), str) and build[key],
                 f"build provenance missing: {key}")
    _require(build.get("stock_libllama_sha256") != build.get("patched_libllama_sha256")
             and build.get("stock_libllama_sha256")
             and build.get("patched_libllama_sha256"),
             "stock and patched libllama not distinguishable")
    raw: dict[str, dict[str, Any]] = {}
    logits: dict[tuple[str, str], tuple[bytes, list[float]]] = {}
    for arm in ARMS:
        item = _json(root / arm / "raw.json")
        _require(item.get("schema") == RAW_SCHEMA and item.get("arm") == arm
                 and "decision" not in item,
                 f"{arm}: raw schema/arm/decision invalid")
        _require(item.get("layer") == 0 and item.get("ngl") == 0
                 and item.get("threads") == 12,
                 f"{arm}: frozen execution configuration mismatch")
        _require([item.get(key) for key in ("first_token", "second_token", "third_token")]
                 == [2167, 1309, 316], f"{arm}: token mismatch")
        _require(item.get("committed_decode_return_code") == 0
                 and item.get("continuation_decode_return_code") == 0,
                 f"{arm}: decode return code invalid")
        _require(item.get("gpu_hits") == {"h2": 2, "h3": 3}.get(arm, 0),
                 f"{arm}: gpu_hits invalid")
        for checkpoint in ("a", "b"):
            _require(item.get(f"logits_{checkpoint}_file") == f"logits-{checkpoint}.f32",
                     f"{arm}: logits path mismatch")
            vector = _floats(root / arm / f"logits-{checkpoint}.f32", 201088)
            expected_token = 1309 if checkpoint == "a" else 316
            _require(max(range(len(vector[1])), key=vector[1].__getitem__) == expected_token,
                     f"{arm}: logits argmax mismatch")
            logits[(arm, checkpoint)] = vector
        runtime = _json(root / arm / "runtime-provenance.json")
        _require(runtime.get("status") == "PASS", f"{arm}: runtime provenance failed")
        resources = _json(root / arm / "resource-summary.json")
        _require(resources.get("status") == "PASS"
                 and resources.get("gpu_failed_samples") == 0
                 and resources.get("peak_process_swap_bytes") == 0,
                 f"{arm}: resource gate failed")
        raw[arm] = item

    result_arms: dict[str, dict[str, Any]] = {}
    route_weights: list[float] | None = None
    for arm in ARMS:
        item = raw[arm]
        if arm in ("stock", "null"):
            _require(item.get("inventory_file") is None
                     and all(item.get(key) == 0 for key in (
                         "prefix_compute_count", "middle_compute_count",
                         "suffix_compute_count", "injected_output_count")),
                     f"{arm}: stock scheduler control altered")
        else:
            _inventory(root, arm, item)
            _require(item.get("stock_capture_rollback") is True
                     and item.get("handoff_capture_rollback") is True,
                     f"{arm}: capture rollback failed")
            _require(item.get("selected_experts") == [1, 13, 17, 21],
                     f"{arm}: route identity failed")
            weights = item.get("routing_weights")
            _require(isinstance(weights, list) and len(weights) == 4
                     and all(type(x) in (int, float) and math.isfinite(x) for x in weights),
                     f"{arm}: weights invalid")
            if route_weights is None:
                route_weights = weights
            _require(weights == route_weights, f"{arm}: routing weights drift")
            _require(item.get("ffn_reference_file") == "ffn-reference.f32"
                     and item.get("ffn_candidate_file") == "ffn-candidate.f32",
                     f"{arm}: FFN vector path mismatch")
            ffn = _parity(_floats(root / arm / "ffn-reference.f32", 2880),
                          _floats(root / arm / "ffn-candidate.f32", 2880))
            _require(ffn["status"] == "PASS"
                     and ffn["bitwise_equal"] == item.get("ffn_bitwise"),
                     f"{arm}: FFN parity failed")
            if arm == "skip-stock":
                _require(ffn["bitwise_equal"], "skip-stock vector not bitwise stock")
            if arm != "segmented":
                _require(item.get("injected_bytes_verified") is True,
                         f"{arm}: injection write not verified")
            result_arms[arm] = {"ffn_parity": ffn, "ffn_bitwise": ffn["bitwise_equal"]}
        checkpoints = {}
        for checkpoint in ("a", "b"):
            parity = _parity(logits[("stock", checkpoint)], logits[(arm, checkpoint)])
            _require(parity["status"] == "PASS", f"{arm}: checkpoint {checkpoint} failed")
            checkpoints[checkpoint] = parity
        result_arms.setdefault(arm, {}).update({
            "tokens": [2167, 1309, 316],
            "checkpoint_a": checkpoints["a"],
            "checkpoint_b": checkpoints["b"],
        })
    return {
        "schema": SUMMARY_SCHEMA,
        "classification": "MEASURED_LIVE_MOE_SPLIT_GRAPH_SKIP_EXACTNESS",
        "status": "PASS",
        "decision": DECISION,
        "stock_tokens": [2167, 1309, 316],
        "logits_count": 201088,
        "arms": result_arms,
        "claim_boundary": (
            "Layer-0 gpt-oss CPU graph split/skip correctness and committed "
            "continuation only; no performance claim."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = validate(args.root)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(summary["decision"])


if __name__ == "__main__":
    main()
