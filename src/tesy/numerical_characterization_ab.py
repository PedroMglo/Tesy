"""Independent, fail-closed analysis of the frozen A+B numerical characterization."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np

VOCAB = 201088
EMBD = 2880
REL_LIMIT = 0.005
COS_LIMIT = 0.9999
N2_DIR = Path("research/vertical-numerical-blocker-20260925/diagnostic-233715")
N1_STOCK_SHA = "52c37d27a8249466a8507211267e5c33fa144eaab060c16bae299bb6d7df7b46"


class CharacterizationError(ValueError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_f32(path: Path, count: int) -> np.ndarray:
    if not path.is_file() or path.stat().st_size != count * 4:
        raise CharacterizationError(f"missing/truncated F32 vector: {path}")
    values = np.fromfile(path, dtype="<f4")
    if values.size != count or not np.isfinite(values).all():
        raise CharacterizationError(f"invalid/non-finite F32 vector: {path}")
    return values


def read_json(path: Path, schema: str) -> dict[str, Any]:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise CharacterizationError(f"duplicate JSON key {key}: {path}")
            result[key] = value
        return result

    raw = json.loads(path.read_text(), object_pairs_hook=unique_pairs)
    if not isinstance(raw, dict) or raw.get("schema") != schema:
        raise CharacterizationError(f"invalid schema: {path}")
    return raw


def validate_resource_trace(path: Path) -> dict[str, int]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line]
    valid_flags = [set(row.get("process", {})) == {"VmRSS_bytes", "VmSwap_bytes"} for row in rows]
    if sum(valid_flags) < 2:
        raise CharacterizationError(f"insufficient resource samples: {path}")
    last_valid = max(i for i, flag in enumerate(valid_flags) if flag)
    if not all(valid_flags[: last_valid + 1]):
        raise CharacterizationError(f"nonterminal process telemetry gap: {path}")
    if any(row.get("gpu", {}).get("status") != "OK" for row in rows):
        raise CharacterizationError(f"GPU telemetry failed: {path}")
    for row in rows[: last_valid + 1]:
        gpu = row["gpu"]
        if row["process"]["VmSwap_bytes"] != 0 or not all(
            math.isfinite(gpu[name]) for name in ("temperature_c", "power_w")
        ):
            raise CharacterizationError(f"invalid resource sample: {path}")
    return {
        "valid_samples": sum(valid_flags),
        "terminal_samples_excluded": len(rows) - sum(valid_flags),
        "nonterminal_gaps": 0,
    }


def placement_from_log(path: Path) -> dict[str, str]:
    rows = re.findall(
        r"load_tensors: layer\s+(\d+) assigned to device\s+(\S+)",
        path.read_text(),
    )
    if len(rows) != 25 or {int(index) for index, _ in rows} != set(range(25)):
        raise CharacterizationError(f"incomplete effective placement log: {path}")
    return {index: device for index, device in rows}


def validate_provenance(runtime: dict[str, Any], build: dict[str, Any]) -> None:
    if (
        runtime.get("status") != "PASS"
        or runtime.get("argv", {}).get("status") != "PASS"
        or runtime.get("argv", {}).get("expected") != runtime.get("argv", {}).get("observed")
        or runtime.get("executable", {}).get("sha256") != build.get("tool_sha256")
        or runtime.get("ggml_cuda", {}).get("sha256") != build.get("libggml_cuda_sha256")
        or runtime.get("mismatches") != []
    ):
        raise CharacterizationError("runtime executable/argv/CUDA provenance mismatch")


def metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    if (
        reference.shape != candidate.shape
        or not np.isfinite(reference).all()
        or not np.isfinite(candidate).all()
    ):
        raise CharacterizationError("mismatched/non-finite metric operands")
    ref = reference.astype(np.float64)
    cand = candidate.astype(np.float64)
    diff = cand - ref
    max_abs = float(np.max(np.abs(diff)))
    max_ref = float(np.max(np.abs(ref)))
    norm = math.sqrt(float(ref @ ref) * float(cand @ cand))
    cosine = float(ref @ cand) / max(norm, 1e-30)
    return {
        "count": int(ref.size),
        "max_abs": max_abs,
        "max_abs_ref": max_ref,
        "relative_max": max_abs / max(1.0, max_ref),
        "cosine": cosine,
        "bitwise_equal": reference.tobytes() == candidate.tobytes(),
    }


def contract(value: dict[str, Any]) -> str:
    return "PASS" if value["relative_max"] <= REL_LIMIT and value["cosine"] >= COS_LIMIT else "FAIL"


def analyze_a(repo: Path, root: Path) -> dict[str, Any]:
    raw = read_json(root / "down-matrix-raw.json", "tesy.numerical_down_matrix_raw.v1")
    read_json(root / "raw.json", "tesy.numerical_characterization_a_raw.v1")
    build = read_json(root / "build-provenance.json", "tesy.vertical_live_build_provenance.v1")
    runtime = read_json(
        root / "runtime-provenance.json", "tesy.mixed_residency_runtime_provenance.v1"
    )
    if (
        build.get("status") != "PASS"
        or build.get("llama_base_head") != "4e416ee7308dd6b581796f1a6241276cd5982691"
        or build.get("model_sha256")
        != "52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4"
        or build.get("model_size_bytes") != 12109564352
        or build.get("prompt_sha256")
        != "99b2641845df47370c29f1661ccb7493bb51ce11dd26a0f3afabb5c49cf18710"
    ):
        raise CharacterizationError("A model/source/workload provenance mismatch")
    validate_provenance(runtime, build)
    a_health = validate_resource_trace(root / "resources.jsonl")
    a_resources = read_json(
        root / "resource-summary.json", "tesy.vertical_live_resource_summary.v1"
    )
    if (
        a_resources.get("status") != "PASS"
        or a_resources.get("valid_samples") != a_health["valid_samples"]
    ):
        raise CharacterizationError("A resource summary contradicts samples")
    manifest = read_json(
        repo / "research/vertical-numerical-blocker-20260925/evidence-manifest-n2.json",
        "tesy.vertical_numerical_diagnostic_evidence_manifest.v1",
    )
    listed = {x["path"]: x for x in manifest["files"]}
    sidecars: dict[str, np.ndarray] = {}
    for arm in ("stock", "mixed"):
        for stage in ("ffn_moe_swiglu_oai", "ffn_moe_down"):
            name = f"layer2-{arm}-{stage}.f32"
            path = repo / N2_DIR / name
            if (
                digest(path) != listed[name]["sha256"]
                or path.stat().st_size != listed[name]["size_bytes"]
            ):
                raise CharacterizationError(f"N2 sidecar identity mismatch: {name}")
            sidecars[name] = read_f32(path, EMBD * 4).reshape(4, EMBD)
    if raw.get("route") != [4, 0, 31, 17] or raw.get("slot") != 1 or raw.get("expert") != 0:
        raise CharacterizationError("A slot/expert/route mapping mismatch")
    if raw.get("cpu_ids") != [4, 0, 31, 17] or raw.get("gpu_local_ids") != [0]:
        raise CharacterizationError("A backend ID mapping mismatch")
    if (
        raw.get("cpu_slots") != 4
        or raw.get("gpu_slots") != 1
        or raw.get("replay_nodes") != 1
        or raw.get("repetitions") != 2
    ):
        raise CharacterizationError("A operator cardinality/topology/repetition mismatch")
    vectors: dict[str, np.ndarray] = {}
    repeated: dict[str, bool] = {}
    hashes: dict[str, list[str]] = {}
    for arm in ("C_xC", "C_xG", "G_xC", "G_xG"):
        paths = [root / f"{arm}-r{i}.f32" for i in (1, 2)]
        first, second = (read_f32(p, EMBD) for p in paths)
        repeated[arm] = first.tobytes() == second.tobytes()
        vectors[arm] = first
        hashes[arm] = [digest(p) for p in paths]
        if raw["repeat_bitwise"].get(arm) is not repeated[arm]:
            raise CharacterizationError("A native repeat flag contradicts vectors")
    diagonal = {
        "C_xC": vectors["C_xC"].tobytes() == sidecars["layer2-stock-ffn_moe_down.f32"][1].tobytes(),
        "G_xG": vectors["G_xG"].tobytes() == sidecars["layer2-mixed-ffn_moe_down.f32"][1].tobytes(),
    }
    if raw["diagonal_bitwise"] != diagonal:
        raise CharacterizationError("A native diagonal flag contradicts sidecars")
    contrasts = {
        "CPU_input": ("C_xC", "C_xG"),
        "GPU_input": ("G_xC", "G_xG"),
        "backend_on_stock_input": ("C_xC", "G_xC"),
        "backend_on_mixed_input": ("C_xG", "G_xG"),
        "total": ("C_xC", "G_xG"),
    }
    comparisons = {name: metrics(vectors[a], vectors[b]) for name, (a, b) in contrasts.items()}
    c_c, c_g, g_c, g_g = (vectors[k].astype(np.float64) for k in ("C_xC", "C_xG", "G_xC", "G_xG"))
    total = g_g - c_c
    decomposition = {
        "gpu_input_plus_backend_stock_input_max_abs_residual": float(
            np.max(np.abs(total - ((g_g - g_c) + (g_c - c_c))))
        ),
        "backend_mixed_input_plus_cpu_input_max_abs_residual": float(
            np.max(np.abs(total - ((g_g - c_g) + (c_g - c_c))))
        ),
    }
    return {
        "execution_status": "PASS",
        "diagnostic_result": "COMPLETE"
        if all(repeated.values()) and all(diagonal.values())
        else "INCONCLUSIVE_REPLAY_NOT_IDENTICAL",
        "comparison_under_existing_contract": "TESY_N2_FAIL_UNCHANGED",
        "sidecar_sha256": {k: listed[k]["sha256"] for k in sidecars},
        "output_sha256": hashes,
        "repeated_bitwise": repeated,
        "diagonal_bitwise": diagonal,
        "comparisons": comparisons,
        "decomposition_float64": decomposition,
        "resource_trace": a_health,
    }


def top(values: np.ndarray) -> dict[str, Any]:
    indices = np.argpartition(values, -2)[-2:]
    ordered = indices[np.argsort(values[indices])[::-1]]
    return {
        "argmax": int(np.argmax(values)),
        "top1_top2_margin": float(np.float64(values[ordered[0]]) - np.float64(values[ordered[1]])),
    }


def analyze_b(repo: Path, root: Path) -> dict[str, Any]:
    build = read_json(root / "build-provenance.json", "tesy.stock_prefix_build_provenance.v1")
    if (
        build.get("status") != "PASS"
        or build.get("llama_head") != "4e416ee7308dd6b581796f1a6241276cd5982691"
    ):
        raise CharacterizationError("B build is not pinned stock")
    if (
        build.get("model_sha256")
        != "52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4"
        or build.get("model_size_bytes") != 12109564352
    ):
        raise CharacterizationError("B model identity changed")
    expected_prompts = {
        "historical": "99b2641845df47370c29f1661ccb7493bb51ce11dd26a0f3afabb5c49cf18710",
        "code": "6cab5251b0045b55cbf0dc7212a1c5f799e7777ca6712731933fce9cf7650327",
    }
    runs: dict[str, Any] = {}
    vectors: dict[str, dict[str, np.ndarray]] = {}
    for label, prompt_sha in expected_prompts.items():
        prompt = (
            repo
            / "benchmarks/prompts"
            / (
                "vertical-short-summary.txt"
                if label == "historical"
                else "vertical-eval-code-short.txt"
            )
        )
        if digest(prompt) != prompt_sha:
            raise CharacterizationError(f"B prompt identity changed: {label}")
        for repeat in (1, 2):
            for ngl in (0, 12):
                key = f"{label}-r{repeat}-ngl{ngl}"
                path = root / key
                raw = read_json(path / "raw.json", "tesy.stock_prefix_logits_raw.v1")
                prov = read_json(
                    path / "runtime-provenance.json", "tesy.mixed_residency_runtime_provenance.v1"
                )
                resources = read_json(
                    path / "resource-summary.json", "tesy.stock_prefix_resource_summary.v1"
                )
                if prov.get("status") != "PASS" or resources.get("status") != "PASS":
                    raise CharacterizationError(f"B runtime/resource failure: {key}")
                validate_provenance(prov, build)
                if (
                    resources.get("peak_process_swap_bytes") != 0
                    or resources.get("gpu_failed_samples") != 0
                    or resources.get("valid_samples", 0) < 2
                ):
                    raise CharacterizationError(f"B missing health evidence: {key}")
                health = validate_resource_trace(path / "resources.jsonl")
                if (
                    resources["valid_samples"] != health["valid_samples"]
                    or resources["terminal_samples_excluded"] != health["terminal_samples_excluded"]
                ):
                    raise CharacterizationError(f"B resource summary contradicts samples: {key}")
                placement = placement_from_log(path / "stderr.txt")
                if (
                    raw.get("n_gpu_layers") != ngl
                    or raw.get("n_ctx") != 4096
                    or raw.get("n_threads") != 12
                    or raw.get("n_vocab") != VOCAB
                ):
                    raise CharacterizationError(f"B run config mismatch: {key}")
                ids = raw.get("prompt_tokens")
                if (
                    not isinstance(ids, list)
                    or not ids
                    or not all(isinstance(x, int) and 0 <= x < VOCAB for x in ids)
                ):
                    raise CharacterizationError(f"B prompt IDs invalid: {key}")
                if raw.get("n_batch") != len(ids) or raw.get("n_ubatch") != len(ids):
                    raise CharacterizationError(f"B batch config mismatch: {key}")
                if raw.get("tokenization") != {"add_special": True, "parse_special": True}:
                    raise CharacterizationError(f"B tokenization mismatch: {key}")
                vectors[key] = {c: read_f32(path / f"{c}.f32", VOCAB) for c in ("P", "D")}
                runs[key] = {
                    "raw": raw,
                    "vectors": {
                        c: {"sha256": digest(path / f"{c}.f32"), **top(vectors[key][c])}
                        for c in ("P", "D")
                    },
                    "resources": resources,
                    "resource_trace": health,
                    "effective_model_layer_placement": placement,
                }
        first_key = f"{label}-r1-ngl0"
        first = runs[first_key]["raw"]
        common = first["greedy_p"]
        if label == "historical" and common != 32:
            raise CharacterizationError("historical first CPU greedy token is not 32")
        for repeat in (1, 2):
            for ngl in (0, 12):
                key = f"{label}-r{repeat}-ngl{ngl}"
                raw = runs[key]["raw"]
                if raw["prompt_tokens"] != first["prompt_tokens"] or raw["common_token"] != common:
                    raise CharacterizationError(f"B compared different prefixes: {key}")
                for checkpoint in ("P", "D"):
                    greedy_key = "greedy_p" if checkpoint == "P" else "greedy_d"
                    if raw[greedy_key] != runs[key]["vectors"][checkpoint]["argmax"]:
                        raise CharacterizationError(
                            f"B greedy token does not equal argmax: {key} {checkpoint}"
                        )
    repeatability: dict[str, Any] = {}
    contrasts: dict[str, Any] = {}
    for label in expected_prompts:
        repeatability[label] = {}
        contrasts[label] = {}
        for ngl in (0, 12):
            repeatability[label][f"ngl{ngl}"] = {}
            for checkpoint in ("P", "D"):
                a = vectors[f"{label}-r1-ngl{ngl}"][checkpoint]
                b = vectors[f"{label}-r2-ngl{ngl}"][checkpoint]
                repeatability[label][f"ngl{ngl}"][checkpoint] = metrics(a, b)
        for repeat in (1, 2):
            contrasts[label][f"r{repeat}"] = {}
            for checkpoint in ("P", "D"):
                a = vectors[f"{label}-r{repeat}-ngl0"][checkpoint]
                b = vectors[f"{label}-r{repeat}-ngl12"][checkpoint]
                comparison = metrics(a, b)
                contrasts[label][f"r{repeat}"][checkpoint] = {
                    **comparison,
                    "contract": contract(comparison),
                    "argmax_b0": top(a)["argmax"],
                    "argmax_b12": top(b)["argmax"],
                }
    historical = all(
        runs[f"historical-r{repeat}-ngl0"]["vectors"]["D"]["sha256"] == N1_STOCK_SHA
        for repeat in (1, 2)
    )
    repeatable = all(
        value["bitwise_equal"]
        for prompt in repeatability.values()
        for arm in prompt.values()
        for value in arm.values()
    )
    all_pass = all(
        value["contract"] == "PASS"
        for prompt in contrasts.values()
        for repeat in prompt.values()
        for value in repeat.values()
    )
    for ngl in (0, 12):
        expected_placement = runs[f"historical-r1-ngl{ngl}"]["effective_model_layer_placement"]
        if any(
            runs[f"{label}-r{repeat}-ngl{ngl}"]["effective_model_layer_placement"]
            != expected_placement
            for label in expected_prompts
            for repeat in (1, 2)
        ):
            raise CharacterizationError("effective placement changed between stock runs")
    return {
        "execution_status": "PASS",
        "diagnostic_result": "COMPLETE"
        if historical and repeatable
        else "INCONCLUSIVE_HISTORICAL_OR_REPEATABILITY",
        "comparison_under_existing_contract": "PASS_OBSERVED_CASES"
        if all_pass
        else "NUMERICAL_CONTRACT_REVIEW_REQUIRED",
        "historical_b0_d_bitwise_n2": historical,
        "repeatable_within_placement_bitwise": repeatable,
        "effective_placement": {
            f"ngl{ngl}": runs[f"historical-r1-ngl{ngl}"]["effective_model_layer_placement"]
            for ngl in (0, 12)
        },
        "runs": runs,
        "repeatability": repeatability,
        "contrasts": contrasts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--a-root", type=Path, required=True)
    parser.add_argument("--b-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise CharacterizationError("refusing to overwrite analysis")
    result = {
        "schema": "tesy.numerical_characterization_ab_analysis.v1",
        "A": analyze_a(args.repo, args.a_root),
        "B": analyze_b(args.repo, args.b_root),
        "tesy_n2_candidate_requalified": False,
        "pending_external_audit": True,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
