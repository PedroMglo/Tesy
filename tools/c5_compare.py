#!/usr/bin/env python3
"""Strict C5 full-logit comparator; shape divergence is a diagnostic outcome."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import struct

from c2_gate import strict_json
from c3_compare_capture_logits import resources

ROOT = Path(__file__).resolve().parents[1]
MODEL = "/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf"
IDS = "results/c3-p1-latency-ids01.tsv"
IDS_SHA = "368c48ac1e93d68ec1746bb3d5f7e63118f35d7903c58f88dbe5c983b69190fb"
MODEL_SHA = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
BACKEND_SHA = "1248fd8fa8cfebaece5ea992e4d951c1e18bb9d5"
VOCAB = 201088
BINARIES = {"A1": ("tools/c4_prefill_probe", "37357baa6b822dacdfb8182b778ee0d27b2737ede5419d7c3b0eb3d826990964", 32),
            "A2": ("tools/c4_prefill_probe", "37357baa6b822dacdfb8182b778ee0d27b2737ede5419d7c3b0eb3d826990964", 32),
            "B1": ("tools/c4_ub64_probe", "b086b7920dc2bdac35f21cd5209f504b61d954ea54aab297b2db8aad0e930b29", 64),
            "B2": ("tools/c4_ub64_probe", "b086b7920dc2bdac35f21cd5209f504b61d954ea54aab297b2db8aad0e930b29", 64)}


class EvidenceError(ValueError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def token_sha():
    path = ROOT / IDS
    if sha(path) != IDS_SHA:
        raise EvidenceError("frozen ID TSV hash changed")
    line = path.read_text().splitlines()[0]
    name, values = line.split("\t", 1)
    ids = [int(x) for x in values.split(",")]
    if name != "latency-short" or len(ids) != 113 or any(x < 0 for x in ids):
        raise EvidenceError("frozen first ID row changed")
    return hashlib.sha256(struct.pack("<113i", *ids)).hexdigest()


def metadata(state_id, ids_hash, vocab=VOCAB):
    return {"state_id": state_id, "token_ids_sha256": ids_hash,
            "position": 112, "sequence_id": 0, "output_mask": "final-token-only",
            "dtype": "f32le", "shape": [vocab], "strides": [4]}


def validate_blob(payload, meta, expected_vocab=VOCAB):
    fields = {"state_id", "token_ids_sha256", "position", "sequence_id",
              "output_mask", "dtype", "shape", "strides"}
    if set(meta) != fields or not isinstance(meta["state_id"], str) or not meta["state_id"]:
        raise EvidenceError("missing/extra metadata or empty state ID")
    if meta["dtype"] != "f32le" or meta["shape"] != [expected_vocab] or \
       meta["strides"] != [4] or len(payload) != expected_vocab * 4:
        raise EvidenceError("dtype/shape/stride or byte count changed")
    if meta["position"] != 112 or meta["sequence_id"] != 0 or \
       meta["output_mask"] != "final-token-only" or \
       not isinstance(meta["token_ids_sha256"], str) or len(meta["token_ids_sha256"]) != 64:
        raise EvidenceError("token/sequence/output metadata changed")
    values = [row[0] for row in struct.iter_unpack("<f", payload)]
    if any(not math.isfinite(v) for v in values):
        raise EvidenceError("non-finite logit")
    return values


def validate_records(records, expected_vocab=VOCAB):
    seen = set()
    values = []
    for payload, meta in records:
        if meta.get("state_id") in seen:
            raise EvidenceError("duplicate state ID")
        seen.add(meta.get("state_id"))
        values.append(validate_blob(payload, meta, expected_vocab))
    if not records:
        raise EvidenceError("empty row set")
    if len({m["token_ids_sha256"] for _, m in records}) != 1:
        raise EvidenceError("token IDs differ")
    return values


def topk(values, k=5):
    best = sorted(range(len(values)), key=lambda i: (-values[i], i))[:k]
    return [{"id": i, "logit": values[i]} for i in best]


def quantile_sorted(values, p):
    # Fixed linear interpolation of sorted finite absolute differences.
    at = (len(values) - 1) * p
    low = int(at)
    high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (at - low)


def pair(left_bytes, left, right_bytes, right):
    if len(left_bytes) != len(right_bytes) or len(left) != len(right) or not left:
        raise EvidenceError("pair shape mismatch")
    delta = [b - a for a, b in zip(left, right)]
    n = len(delta)
    abs_delta = sorted(abs(x) for x in delta)
    centered = sum(delta) / n
    max_idx = max(range(n), key=lambda i: abs(delta[i]))
    float_equal = sum(a == b for a, b in zip(left, right))
    byte_equal = sum(left_bytes[i*4:(i+1)*4] == right_bytes[i*4:(i+1)*4]
                     for i in range(n))
    max_a, max_b = max(left), max(right)
    ea = [math.exp(x - max_a) for x in left]
    eb = [math.exp(x - max_b) for x in right]
    za, zb = sum(ea), sum(eb)
    pa = [x / za for x in ea]
    pb = [x / zb for x in eb]
    ta, tb = topk(left), topk(right)
    return {
        "count": n, "bitwise_equal_count": byte_equal, "float_equal_count": float_equal,
        "signed_zero_byte_mismatch_count": sum(a == b == 0.0 and left_bytes[i*4:(i+1)*4] != right_bytes[i*4:(i+1)*4]
                                                for i, (a, b) in enumerate(zip(left, right))),
        "first_different_index": next((i for i in range(n) if left_bytes[i*4:(i+1)*4] != right_bytes[i*4:(i+1)*4]), None),
        "max_abs": abs_delta[-1], "max_abs_index": max_idx,
        "mean_abs": sum(abs_delta) / n,
        "rmse": math.sqrt(sum(x*x for x in delta) / n),
        "abs_quantiles": {str(p): quantile_sorted(abs_delta, p) for p in (0.5, 0.9, 0.99, 0.999)},
        "signed_mean_delta_right_minus_left": centered,
        "centered_max_abs": max(abs(x - centered) for x in delta),
        "centered_rmse": math.sqrt(sum((x-centered)**2 for x in delta) / n),
        "top5_left": ta, "top5_right": tb,
        "top1_margin_left": ta[0]["logit"] - ta[1]["logit"],
        "top1_margin_right": tb[0]["logit"] - tb[1]["logit"],
        "softmax_total_variation": 0.5 * sum(abs(a-b) for a, b in zip(pa, pb)),
        "softmax_max_abs": max(abs(a-b) for a, b in zip(pa, pb)),
    }


def load_run(arm, stem, ids_hash):
    expected_binary, binary_sha, ubatch = BINARIES[arm]
    stem = Path(stem)
    if stem.parent != ROOT / "results" or not stem.name.startswith("c5-d1-"):
        raise EvidenceError("unexpected run root")
    mpath = Path(str(stem) + ".json")
    manifest = strict_json(mpath.read_text())
    if manifest.get("run_id") != stem.name or manifest.get("backend_sha") != BACKEND_SHA or \
       manifest.get("model_path") != MODEL or \
       manifest.get("artifact_identity", {}).get("sha256_previously_verified") != MODEL_SHA or \
       manifest.get("workload_sha256") != IDS_SHA or \
       manifest.get("binary_sha256") != binary_sha:
        raise EvidenceError(f"{arm}: provenance mismatch")
    command = manifest.get("command")
    if command != [expected_binary, MODEL, IDS, str(stem.relative_to(ROOT)), "short"]:
        raise EvidenceError(f"{arm}: command differs from frozen schedule")
    if manifest.get("explicit_env") != {"LLAMA_MOE_STREAM_NO_PRELOAD": "1"}:
        raise EvidenceError(f"{arm}: preload environment changed")
    if manifest.get("limits", {}).get("max_rss_gib") != 17.0 or \
       manifest["limits"].get("max_gpu_mib") != 7000.0 or \
       manifest["limits"].get("min_available_gib") != 6.0 or \
       manifest["limits"].get("max_cpu_c") != 95.0 or \
       manifest["limits"].get("max_gpu_c") != 80.0 or \
       manifest["limits"].get("max_nvme_c") != 70.0 or \
       not manifest["limits"].get("require_telemetry"):
        raise EvidenceError(f"{arm}: resource policy changed")
    resources(manifest, Path(str(stem) + ".samples.jsonl"))
    row_path = Path(str(stem) + ".rows.tsv")
    if row_path.read_text() != "case\trow\ttokens\nlatency-short\t0\t113\n":
        raise EvidenceError(f"{arm}: row/output mask changed")
    rows = list(csv.DictReader(Path(str(stem) + ".cases.tsv").open(), delimiter="\t"))
    if len(rows) != 1 or rows[0].get("case") != "latency-short" or rows[0].get("tokens") != "113":
        raise EvidenceError(f"{arm}: timing/ID row invalid")
    payload_path = Path(str(stem) + ".f32")
    payload = payload_path.read_bytes()
    meta = metadata("latency-short:seq0:pos112", ids_hash)
    values = validate_blob(payload, meta)
    sources = {p.name: sha(p) for p in
               (mpath, row_path, Path(str(stem) + ".cases.tsv"), payload_path,
                Path(str(stem) + ".samples.jsonl"), Path(str(stem) + ".stderr"))}
    return {"arm": arm, "run_id": stem.name, "ubatch": ubatch,
            "manifest": manifest, "payload": payload, "values": values,
            "metadata": meta, "sources_sha256": sources}


def write_new(path, obj):
    with Path(path).open("x") as out:
        json.dump(obj, out, indent=2, allow_nan=False)
        out.write("\n")


def main():
    p = argparse.ArgumentParser()
    for arm in ("A1", "B1", "B2", "A2"):
        p.add_argument(arm, type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        p.error("no-replace report exists")
    try:
        ids_hash = token_sha()
        arms = {arm: load_run(arm, (ROOT / getattr(args, arm)).resolve(), ids_hash)
                for arm in ("A1", "B1", "B2", "A2")}
        if len({r["run_id"] for r in arms.values()}) != 4:
            raise EvidenceError("duplicate run IDs")
        for key in ("model_id", "model_path", "artifact_identity", "backend_sha",
                    "backend_libraries_sha256", "workload_sha256"):
            if len({json.dumps(r["manifest"][key], sort_keys=True) for r in arms.values()}) != 1:
                raise EvidenceError(f"arm provenance mismatch: {key}")
        comparisons = {}
        for left, right in (("A1", "A2"), ("B1", "B2"), ("A1", "B1"), ("A2", "B2")):
            a, b = arms[left], arms[right]
            if a["metadata"] != b["metadata"]:
                raise EvidenceError("comparison metadata differs")
            comparisons[f"{left}:{right}"] = pair(a["payload"], a["values"],
                                                    b["payload"], b["values"])
        stable = all(comparisons[key]["bitwise_equal_count"] == VOCAB
                     for key in ("A1:A2", "B1:B2"))
        cross = any(comparisons[key]["bitwise_equal_count"] < VOCAB
                    for key in ("A1:B1", "A2:B2"))
        status = ("FORM_STABLE_CROSS_FORM_DIVERGENCE" if stable and cross else
                  "WITHIN_FORM_VARIABILITY" if not stable else "NO_CROSS_FORM_DIVERGENCE")
        result = {"schema": "c5-d1-numeric-v1", "status": status,
                  "scope": "full final pre-sampler logits; one external 113-token decode per fresh process",
                  "token_ids_sha256": ids_hash,
                  "arms": {arm: {key: value for key, value in row.items()
                                 if key in ("run_id", "ubatch", "metadata", "sources_sha256")}
                           for arm, row in arms.items()},
                  "comparisons": comparisons,
                  "analyzer_sha256": sha(__file__)}
    except (OSError, KeyError, TypeError, ValueError) as exc:
        result = {"schema": "c5-d1-numeric-v1", "status": "FAIL_EVIDENCE",
                  "reason": f"{type(exc).__name__}: {exc}"}
    write_new(args.output, result)
    print(json.dumps({"status": result["status"], "reason": result.get("reason")}))
    return 0 if result["status"] == "FORM_STABLE_CROSS_FORM_DIVERGENCE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
