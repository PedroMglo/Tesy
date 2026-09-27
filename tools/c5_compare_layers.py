#!/usr/bin/env python3
"""Align C5 layer observer rows by absolute token, then find first difference."""

import csv
import hashlib
import json
import math
from pathlib import Path
import struct

from c2_gate import strict_json
from c3_compare_capture_logits import resources
from c5_compare import EvidenceError, IDS, IDS_SHA, MODEL, MODEL_SHA, BACKEND_SHA, ROOT, VOCAB, write_new

CAPTURE_BIN_SHA = "41d2492c49cc8daad733cc936a804d886b499b9234acfa3d5bd5930e88dbb3e5"
STEMS = {"A": ROOT / "results/c5-d2-capture-a-ub32-02",
         "B": ROOT / "results/c5-d2-capture-b-ub64-02"}
CONTROLS = {"A": ROOT / "results/c5-d1-a1-ub32-short01",
            "B": ROOT / "results/c5-d1-b1-ub64-short01"}
OUT = ROOT / "results/c5-d2-layer-comparison01.json"
INDEX_COLUMNS = ["chunk", "stage", "layer", "first_abs", "n_tokens",
                 "type", "ne", "nb", "bytes", "file"]
ROW_BYTES = 2880 * 4


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_index(root, ubatch):
    path = root / "index.tsv"
    with path.open() as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    if not rows or list(rows[0]) != INDEX_COLUMNS:
        raise EvidenceError("capture index empty or schema changed")
    sizes = [min(ubatch, 113 - off) for off in range(0, 113, ubatch)]
    starts = [sum(sizes[:i]) for i in range(len(sizes))]
    expected = {(chunk, "attn_norm", 0) for chunk in range(len(sizes))}
    expected |= {(chunk, "l_out", layer)
                 for chunk in range(len(sizes)) for layer in range(36)}
    seen = set()
    data = {}
    hashes = {}
    for row in rows:
        try:
            chunk, layer = int(row["chunk"]), int(row["layer"])
            first, n = int(row["first_abs"]), int(row["n_tokens"])
            shape = tuple(int(x) for x in row["ne"].split(","))
            stride = tuple(int(x) for x in row["nb"].split(","))
            count = int(row["bytes"])
        except (ValueError, TypeError) as exc:
            raise EvidenceError("malformed capture integer") from exc
        key = (chunk, row["stage"], layer)
        if key not in expected or key in seen:
            raise EvidenceError("unexpected/duplicate capture state")
        seen.add(key)
        if row["type"] != "f32" or len(shape) != 4 or len(stride) != 4 or \
           shape[0] != 2880 or shape[2:] != (1, 1) or stride[0] != 4 or \
           stride[1] < ROW_BYTES:
            raise EvidenceError("capture dtype/shape/stride invalid")
        if row["stage"] == "attn_norm" or layer < 35:
            if n != sizes[chunk] or first != starts[chunk]:
                raise EvidenceError("normal-layer token coverage changed")
        elif chunk < len(sizes)-1:
            if n != 0 or first != -1:
                raise EvidenceError("non-final last layer has output rows")
        elif n != 1 or first != 112:
            raise EvidenceError("last requested output token changed")
        if shape[1] != n or count != n*ROW_BYTES:
            raise EvidenceError("activation count inconsistent with shape")
        if n == 0:
            if row["file"] != "-":
                raise EvidenceError("zero-row tensor has file")
            continue
        filename = row["file"]
        if filename != f"chunk{chunk}_{row['stage']}_{layer}.f32":
            raise EvidenceError("capture filename/state mismatch")
        file = root / filename
        payload = file.read_bytes()
        if len(payload) != count or any(not math.isfinite(x[0])
                                        for x in struct.iter_unpack("<f", payload)):
            raise EvidenceError("truncated/non-finite logical activation")
        data[key] = payload
        hashes[filename] = hashlib.sha256(payload).hexdigest()
    if seen != expected:
        raise EvidenceError("missing capture state")
    return {"sizes": sizes, "starts": starts, "data": data, "hashes": hashes,
            "index_sha256": sha(path), "rows": len(rows)}


def inspect(arm, ubatch):
    stem = STEMS[arm]
    raw = Path(str(stem) + ".raw")
    manifest = strict_json(Path(str(stem) + ".json").read_text())
    if manifest.get("run_id") != stem.name or manifest.get("backend_sha") != BACKEND_SHA or \
       manifest.get("model_path") != MODEL or \
       manifest.get("artifact_identity", {}).get("sha256_previously_verified") != MODEL_SHA or \
       manifest.get("workload_sha256") != IDS_SHA or \
       manifest.get("binary_sha256") != CAPTURE_BIN_SHA or \
       manifest.get("explicit_env") != {"LLAMA_MOE_STREAM_NO_PRELOAD": "1"}:
        raise EvidenceError(f"{arm}: capture provenance mismatch")
    expected_command = ["tools/c5_capture_probe", MODEL, IDS,
                        str(stem.relative_to(ROOT)), "short", "--ubatch", str(ubatch)]
    if manifest.get("command") != expected_command:
        raise EvidenceError(f"{arm}: capture command changed")
    resources(manifest, Path(str(stem) + ".samples.jsonl"))
    stderr = Path(str(stem) + ".stderr").read_text()
    if "offloaded 8/37 layers to GPU" not in stderr:
        raise EvidenceError("production placement not observed")
    row_path = Path(str(stem) + ".rows.tsv")
    if row_path.read_text() != "case\trow\ttokens\nlatency-short\t0\t113\n":
        raise EvidenceError("observer output mask/row changed")
    captured = Path(str(stem) + ".f32").read_bytes()
    reference = Path(str(CONTROLS[arm]) + ".f32").read_bytes()
    if len(captured) != VOCAB*4 or len(reference) != VOCAB*4:
        raise EvidenceError("observer/control logits incomplete")
    index = parse_index(raw, ubatch)
    return {"manifest_sha256": sha(Path(str(stem) + ".json")),
            "stderr_sha256": sha(Path(str(stem) + ".stderr")),
            "captured_logits_sha256": hashlib.sha256(captured).hexdigest(),
            "control_logits_sha256": hashlib.sha256(reference).hexdigest(),
            "neutral_bitwise": captured == reference, "index": index}


def aligned(index, stage, layer):
    chunks = [index["data"][(i, stage, layer)] for i in range(len(index["sizes"]))]
    payload = b"".join(chunks)
    if len(payload) != 113*ROW_BYTES:
        raise EvidenceError("aligned logical activation has missing tokens")
    return payload


def difference(left, right):
    if len(left) != len(right) or len(left) != 113*ROW_BYTES:
        raise EvidenceError("aligned pair shape mismatch")
    if left == right:
        return {"bitwise_equal": True, "sha256": hashlib.sha256(left).hexdigest()}
    first = next(i for i in range(0, len(left), 4) if left[i:i+4] != right[i:i+4])
    a = (x[0] for x in struct.iter_unpack("<f", left))
    b = (x[0] for x in struct.iter_unpack("<f", right))
    max_abs = 0.0
    unequal = 0
    sum_sq = 0.0
    for x, y in zip(a, b):
        delta = y-x
        if delta:
            unequal += 1
        max_abs = max(max_abs, abs(delta))
        sum_sq += delta*delta
    return {"bitwise_equal": False, "left_sha256": hashlib.sha256(left).hexdigest(),
            "right_sha256": hashlib.sha256(right).hexdigest(),
            "first_abs_token": first//ROW_BYTES,
            "first_feature": (first//4) % 2880,
            "different_float_count": unequal,
            "max_abs": max_abs,
            "rmse": math.sqrt(sum_sq/(113*2880))}


def main():
    if OUT.exists():
        raise SystemExit("no-replace report exists")
    try:
        arms = {"A": inspect("A", 32), "B": inspect("B", 64)}
        if not all(x["neutral_bitwise"] for x in arms.values()):
            status = "OBSERVER_EFFECT"
            comparisons = {}
        else:
            index_a, index_b = arms["A"]["index"], arms["B"]["index"]
            comparisons = {"attn_norm_0": difference(aligned(index_a,"attn_norm",0),
                                                      aligned(index_b,"attn_norm",0))}
            first = None
            for layer in range(35):
                result = difference(aligned(index_a,"l_out",layer),
                                    aligned(index_b,"l_out",layer))
                comparisons[f"l_out_{layer}"] = result
                if not result["bitwise_equal"]:
                    first = layer
                    break
            status = "FIRST_LAYER_OBSERVED" if first is not None else "NO_NORMAL_LAYER_DIFFERENCE"
        report = {"schema": "c5-d2-layer-v1", "status": status,
                  "scope": "113 logical token positions, seq0, source callback layer output; capture timing diagnostic",
                  "first_different_l_out_layer": first if status == "FIRST_LAYER_OBSERVED" else None,
                  "comparisons": comparisons,
                  "arms": {arm: {k: v for k, v in row.items() if k != "index"} |
                           {"index_sha256": row["index"]["index_sha256"],
                            "index_rows": row["index"]["rows"],
                            "chunks": row["index"]["sizes"]}
                           for arm, row in arms.items()},
                  "analyzer_sha256": sha(__file__)}
    except (OSError, KeyError, TypeError, ValueError) as exc:
        report = {"schema": "c5-d2-layer-v1", "status": "FAIL_EVIDENCE",
                  "reason": f"{type(exc).__name__}: {exc}"}
    write_new(OUT, report)
    print(json.dumps({"status": report["status"], "first_layer": report.get("first_different_l_out_layer"),
                      "reason": report.get("reason")}))
    return 0 if report["status"] == "FIRST_LAYER_OBSERVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
