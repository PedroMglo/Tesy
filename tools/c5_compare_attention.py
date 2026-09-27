#!/usr/bin/env python3
"""Validate and align C5 Flash Attention outputs by absolute token."""

import csv
import hashlib
import json
import math
from pathlib import Path
import struct

from c2_gate import strict_json
from c3_compare_capture_logits import resources
from c5_compare import EvidenceError, IDS, IDS_SHA, MODEL, MODEL_SHA, BACKEND_SHA, ROOT, VOCAB, write_new
from c5_compare_layers import sha

WIDTHS = {"attn_norm": 2880, "Q_proj": 4096, "Q_bias": 4096,
          "Q_reshape": 4096, "Q_rope": 4096, "K_proj": 512,
          "K_bias": 512, "K_reshape": 512, "K_rope": 512,
          "V_proj": 512, "V_bias": 512, "V_reshape": 512,
          "flash_attn": 4096, "kqv_out": 4096,
          "attn_out": 2880}
STAGES = tuple(WIDTHS)
BIN_SHA = "332040dd350664d77007b1e84ace0466368ef445c121d7df768d166c577bde99"
STEMS = {"A": ROOT / "results/c5-d2-attn-a-ub32-01",
         "B": ROOT / "results/c5-d2-attn-b-ub64-01"}
CONTROLS = {"A": ROOT / "results/c5-d1-a1-ub32-short01",
            "B": ROOT / "results/c5-d1-b1-ub64-short01"}
OUT = ROOT / "results/c5-d2-attn-comparison01.json"
HEADER = ["chunk", "stage", "layer", "first_abs", "n_tokens", "type", "ne", "nb", "bytes", "file"]


def difference(left, right, width):
    if len(left) != len(right) or len(left) != 113*width*4:
        raise EvidenceError("aligned QKV shape mismatch")
    if left == right:
        return {"bitwise_equal": True, "sha256": hashlib.sha256(left).hexdigest()}
    first = next(i for i in range(0,len(left),4) if left[i:i+4] != right[i:i+4])//4
    delta = [b[0]-a[0] for a,b in zip(struct.iter_unpack("<f",left),
                                      struct.iter_unpack("<f",right))]
    return {"bitwise_equal": False, "first_abs_token": first//width,
            "first_feature": first%width,
            "different_float_count": sum(x!=0 for x in delta),
            "max_abs": max(abs(x) for x in delta),
            "rmse": math.sqrt(sum(x*x for x in delta)/len(delta)),
            "left_sha256": hashlib.sha256(left).hexdigest(),
            "right_sha256": hashlib.sha256(right).hexdigest()}


def inspect(arm, ubatch):
    stem = STEMS[arm]
    manifest = strict_json(Path(str(stem)+".json").read_text())
    expected_command = ["tools/c5_attention_capture_probe", MODEL, IDS,
                        str(stem.relative_to(ROOT)), "short", "--ubatch", str(ubatch)]
    if manifest.get("run_id") != stem.name or manifest.get("backend_sha") != BACKEND_SHA or \
       manifest.get("model_path") != MODEL or \
       manifest.get("artifact_identity", {}).get("sha256_previously_verified") != MODEL_SHA or \
       manifest.get("workload_sha256") != IDS_SHA or manifest.get("binary_sha256") != BIN_SHA or \
       manifest.get("explicit_env") != {"LLAMA_MOE_STREAM_NO_PRELOAD": "1"} or \
       manifest.get("command") != expected_command:
        raise EvidenceError(f"{arm}: operation observer provenance mismatch")
    resources(manifest, Path(str(stem)+".samples.jsonl"))
    if "offloaded 8/37 layers to GPU" not in Path(str(stem)+".stderr").read_text():
        raise EvidenceError(f"{arm}: production placement absent")
    if Path(str(stem)+".rows.tsv").read_text() != "case\trow\ttokens\nlatency-short\t0\t113\n":
        raise EvidenceError(f"{arm}: output selection changed")
    output = Path(str(stem)+".f32").read_bytes()
    control = Path(str(CONTROLS[arm])+".f32").read_bytes()
    if len(output) != VOCAB*4 or len(control) != VOCAB*4:
        raise EvidenceError(f"{arm}: incomplete final output")
    raw = Path(str(stem)+".raw")
    with (raw/"index.tsv").open() as source:
        reader = csv.DictReader(source, delimiter="\t")
        if reader.fieldnames != HEADER:
            raise EvidenceError(f"{arm}: invalid index schema")
        rows = list(reader)
    sizes = [min(ubatch, 113-offset) for offset in range(0,113,ubatch)]
    starts = [sum(sizes[:i]) for i in range(len(sizes))]
    expected = {(i, stage) for i in range(len(sizes)) for stage in STAGES}
    seen = set()
    payloads = {}
    for row in rows:
        try:
            chunk, layer = int(row["chunk"]), int(row["layer"])
            first, n, count = int(row["first_abs"]), int(row["n_tokens"]), int(row["bytes"])
            ne = tuple(int(x) for x in row["ne"].split(","))
            nb = tuple(int(x) for x in row["nb"].split(","))
        except (ValueError, TypeError) as exc:
            raise EvidenceError(f"{arm}: malformed index integer") from exc
        key = (chunk, row["stage"])
        if key not in expected or key in seen or layer != 0:
            raise EvidenceError(f"{arm}: duplicate/unexpected stage")
        seen.add(key)
        width = WIDTHS[row["stage"]]
        expected_shape = (width, sizes[chunk], 1, 1) if row["stage"] in \
            ("attn_norm", "attn_out", "kqv_out", "Q_proj", "Q_bias", "K_proj", "K_bias", "V_proj", "V_bias") \
            else (64, width//64, sizes[chunk], 1)
        if row["type"] != "f32" or len(ne) != 4 or len(nb) != 4 or \
           ne != expected_shape or nb[0] != 4 or \
           nb[1] < ne[0]*4 or (ne[2]>1 and nb[2] < ne[1]*nb[1]) or \
           first != starts[chunk] or n != sizes[chunk] or count != n*width*4:
            raise EvidenceError(f"{arm}: stage shape/stride/position invalid")
        filename = f"chunk{chunk}_{row['stage']}_0.f32"
        if row["file"] != filename:
            raise EvidenceError(f"{arm}: stage filename mismatch")
        payload = (raw/filename).read_bytes()
        if len(payload) != count or any(not math.isfinite(x[0])
                                        for x in struct.iter_unpack("<f", payload)):
            raise EvidenceError(f"{arm}: truncated/non-finite stage")
        payloads[key] = payload
    if seen != expected:
        raise EvidenceError(f"{arm}: missing stage")
    aligned = {stage: b"".join(payloads[i, stage] for i in range(len(sizes))) for stage in STAGES}
    if any(len(data) != 113*WIDTHS[stage]*4 for stage,data in aligned.items()):
        raise EvidenceError(f"{arm}: incomplete aligned stage")
    return {"neutral_bitwise": output == control, "final_logits_sha256": hashlib.sha256(output).hexdigest(),
            "manifest_sha256": sha(str(stem)+".json"), "index_sha256": sha(raw/"index.tsv"),
            "chunks": sizes, "index_rows": len(rows), "stages": aligned}


def main():
    if OUT.exists():
        raise SystemExit("no-replace report exists")
    try:
        arms = {"A": inspect("A",32), "B": inspect("B",64)}
        comparison = {stage: difference(arms["A"]["stages"][stage], arms["B"]["stages"][stage], WIDTHS[stage])
                      for stage in STAGES} if all(v["neutral_bitwise"] for v in arms.values()) else {}
        report = {"schema": "c5-d2-attn-v1", "status": "FIRST_DIFFERENCE_AT_FLASH_ATTN" if
                  comparison and all(comparison[stage]["bitwise_equal"] for stage in STAGES[:12]) and
                  not comparison["flash_attn"]["bitwise_equal"] else "OBSERVER_OR_STAGE_GATE_FAILED",
                  "comparisons": comparison,
                  "arms": {name: {key: value for key, value in arm.items() if key != "stages"}
                           for name, arm in arms.items()}, "analyzer_sha256": sha(__file__)}
    except (EvidenceError, OSError, KeyError, TypeError, ValueError) as exc:
        report = {"schema": "c5-d2-attn-v1", "status": "FAIL_EVIDENCE",
                  "reason": f"{type(exc).__name__}: {exc}"}
    write_new(OUT, report)
    print(json.dumps({"status": report["status"], "reason": report.get("reason")}))
    return 0 if report["status"] == "FIRST_DIFFERENCE_AT_FLASH_ATTN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
