#!/usr/bin/env python3
"""Compare same-token routing and common-position logits across C4 ubatches."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

from c2_gate import strict_json
from c3_compare_capture_logits import resources
from c3_compare_preload_capture import PHASES, STAGES, check_bytes, indexed

VOCAB_BYTES = 201088 * 4
COMMON_LOGITS = ("prefill_final", "decode0", "decode1", "decode7", "decode31")
STEMS = (Path("results/c4-p1-bridge-ub32-spec01"),
         Path("results/c4-p1-capture-ub64-spec01"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shape(row, stage, n):
    ne = [int(x) for x in row["ne"].split(",")]
    nb = [int(x) for x in row["nb"].split(",")]
    expected = {"attn_post_norm": (2880, n), "ffn_moe_logits": (128, n),
                "ffn_moe_probs": (128, n), "ffn_moe_topk": (4, n),
                "ffn_moe_weights_softmax": (1, 4, n), "ffn_moe_out": (2880, n)}[stage]
    if len(ne) != 4 or len(nb) != 4 or tuple(ne[:len(expected)]) != expected or \
       any(x <= 0 for x in nb) or nb[0] != 4:
        raise ValueError(f"shape/stride mismatch: {stage} expected {expected}, got {ne}/{nb}")
    offset = sum((ne[i] - 1) * nb[i] for i in range(4))
    if offset + 4 > int(row["bytes"]):
        raise ValueError("capture strides exceed payload")
    return ne, nb


def pair_bits(entry, stage, n_common):
    row, file = entry
    ne, nb = shape(row, stage, int(row["ne"].split(",")[2 if stage == "ffn_moe_weights_softmax" else 1]))
    data = file.read_bytes()
    result = []
    for token in range(n_common):
        for k in range(4):
            offset = token * (nb[2] if stage == "ffn_moe_weights_softmax" else nb[1]) + \
                     k * (nb[1] if stage == "ffn_moe_weights_softmax" else nb[0])
            value = data[offset:offset+4]
            if len(value) != 4:
                raise ValueError("short strided routed pair")
            if stage == "ffn_moe_weights_softmax" and \
               not math.isfinite(struct.unpack("<f", value)[0]):
                raise ValueError("nonfinite route weight")
            result.append(value)
    return result


def compare():
    manifests = [strict_json(Path(str(stem)+".json").read_text()) for stem in STEMS]
    for stem, manifest in zip(STEMS, manifests):
        resources(manifest, Path(str(stem)+".samples.jsonl"))
    for key in ("model_id", "model_path", "artifact_identity", "backend_sha",
                "backend_libraries_sha256", "binary_sha256", "workload_sha256",
                "input_files_sha256"):
        if manifests[0][key] != manifests[1][key]:
            raise ValueError(f"provenance mismatch: {key}")
    if any(manifest["explicit_env"].get("LLAMA_MOE_STREAM_NO_PRELOAD") != "1"
           for manifest in manifests):
        raise ValueError("preload mode changed")
    commands = [manifest["command"] for manifest in manifests]
    if commands[0][:-4] != commands[1][:-4] or \
       commands[0][-3:-1] != ["--all-layers", "--ubatch"] or \
       commands[1][-3:-1] != ["--all-layers", "--ubatch"] or \
       [command[-1] for command in commands] != ["32", "64"]:
        raise ValueError("capture command changed beyond output and ubatch")
    roots = [Path(str(stem)+".raw") for stem in STEMS]
    indexed_rows = [indexed(root) for root in roots]
    byte_counts = [check_bytes(root) for root in roots]
    for arm, rows in enumerate(indexed_rows):
        for (phase, layer, stage), (row, _) in rows.items():
            n = 1 if layer == 35 or phase.startswith("decode") else \
                30 if phase == "prefill_final" else (32 if arm == 0 else 64)
            shape(row, stage, n)
    route_mismatch = []
    weight_mismatch = []
    for phase in PHASES:
        for layer in range(36):
            n = 1 if layer == 35 or phase.startswith("decode") else \
                30 if phase == "prefill_final" else 32
            for stage, failures in (("ffn_moe_topk", route_mismatch),
                                    ("ffn_moe_weights_softmax", weight_mismatch)):
                left = pair_bits(indexed_rows[0][(phase, layer, stage)], stage, n)
                right = pair_bits(indexed_rows[1][(phase, layer, stage)], stage, n)
                if left != right:
                    failures.append({"phase": phase, "layer": layer,
                                     "first_pair": next(i for i, (a, b) in enumerate(zip(left, right)) if a != b)})
    vectors = []
    for phase in COMMON_LOGITS:
        paths = [root / f"{phase}.logits.f32" for root in roots]
        payloads = [path.read_bytes() for path in paths]
        if any(len(payload) != VOCAB_BYTES for payload in payloads):
            raise ValueError("full logits vector incomplete")
        if any(not math.isfinite(value) for payload in payloads
               for (value,) in struct.iter_unpack("<f", payload)):
            raise ValueError("nonfinite full logit")
        vectors.append({"phase": phase, "bitwise_equal": payloads[0] == payloads[1],
                        "ub32_sha256": hashlib.sha256(payloads[0]).hexdigest(),
                        "ub64_sha256": hashlib.sha256(payloads[1]).hexdigest()})
    first_stage = None
    for phase in COMMON_LOGITS:
        for layer in range(36):
            for stage in STAGES:
                a, b = (rows[(phase, layer, stage)] for rows in indexed_rows)
                if a[0]["ne"] != b[0]["ne"] or a[0]["nb"] != b[0]["nb"] or \
                   a[1].read_bytes() != b[1].read_bytes():
                    first_stage = {"phase": phase, "layer": layer, "stage": stage}
                    break
            if first_stage:
                break
        if first_stage:
            break
    matched = not route_mismatch and not weight_mismatch and all(x["bitwise_equal"] for x in vectors)
    return {"schema": "c4-p1-ubatch-capture-v1",
            "status": "COMMON_POSITION_BITWISE_PASS" if matched else
                      "NON_BITWISE_REQUIRES_SEPARATE_QUALIFICATION",
            "scope": "same captured token positions only; prefill0/128 external-batch endpoints differ",
            "direct_slice_checks": byte_counts,
            "routed_id_mismatches": route_mismatch[:12],
            "route_weight_mismatches": weight_mismatch[:12],
            "routed_id_mismatch_count": len(route_mismatch),
            "route_weight_mismatch_count": len(weight_mismatch),
            "common_logits": vectors,
            "first_different_captured_stage": first_stage,
            "source_sha256": {str(path): sha(path) for path in
                              (Path(str(STEMS[0])+".json"), Path(str(STEMS[1])+".json"),
                               roots[0]/"index.tsv", roots[1]/"index.tsv",
                               roots[0]/"byte_checks.tsv", roots[1]/"byte_checks.tsv")},
            "analyzer_sha256": sha(Path(__file__))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("no-replace output exists")
    try:
        result = compare()
    except (OSError, ValueError, KeyError, TypeError, struct.error) as exc:
        result = {"schema": "c4-p1-ubatch-capture-v1", "status": "FAIL_EVIDENCE",
                  "reason": f"{type(exc).__name__}: {exc}"}
    with args.output.open("x") as out:
        json.dump(result, out, indent=2, allow_nan=False)
        out.write("\n")
    print(json.dumps({"status": result["status"], "reason": result.get("reason"),
                      "logits": [x["bitwise_equal"] for x in result.get("common_logits", [])],
                      "routes": result.get("routed_id_mismatch_count")}))
    return 0 if result["status"] == "COMMON_POSITION_BITWISE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
