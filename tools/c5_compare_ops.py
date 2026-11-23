#!/usr/bin/env python3
"""Validate and align the six layer-zero stages of the C5 observer."""

import csv
import hashlib
import json
import math
from pathlib import Path
import struct

from c2_gate import strict_json
from c3_compare_capture_logits import resources
from c5_compare import EvidenceError, IDS, IDS_SHA, MODEL, MODEL_SHA, BACKEND_SHA, ROOT, VOCAB, write_new
from c5_compare_layers import difference, sha

STAGES = ("attn_norm", "attn_out", "ffn_inp", "attn_post_norm", "ffn_moe_out", "l_out")
BIN_SHA = "1213da90082a6d8737a089f7ec73dd81229bbd3a79f5a2307b3b6a20e9f8faa4"
STEMS = {"A": ROOT / "results/c5-d2-op-a-ub32-01",
         "B": ROOT / "results/c5-d2-op-b-ub64-01"}
CONTROLS = {"A": ROOT / "results/c5-d1-a1-ub32-short01",
            "B": ROOT / "results/c5-d1-b1-ub64-short01"}
OUT = ROOT / "results/c5-d2-op-comparison01.json"
HEADER = ["chunk", "stage", "layer", "first_abs", "n_tokens", "type", "ne", "nb", "bytes", "file"]
ROW_BYTES = 2880*4


def inspect(arm, ubatch):
    stem = STEMS[arm]
    manifest = strict_json(Path(str(stem)+".json").read_text())
    expected_command = ["tools/c5_op_capture_probe", MODEL, IDS,
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
        if row["type"] != "f32" or len(ne) != 4 or len(nb) != 4 or \
           ne != (2880, sizes[chunk], 1, 1) or nb[0] != 4 or nb[1] < ROW_BYTES or \
           first != starts[chunk] or n != sizes[chunk] or count != n*ROW_BYTES:
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
    if any(len(data) != 113*ROW_BYTES for data in aligned.values()):
        raise EvidenceError(f"{arm}: incomplete aligned stage")
    return {"neutral_bitwise": output == control, "final_logits_sha256": hashlib.sha256(output).hexdigest(),
            "manifest_sha256": sha(str(stem)+".json"), "index_sha256": sha(raw/"index.tsv"),
            "chunks": sizes, "index_rows": len(rows), "stages": aligned}


def main():
    if OUT.exists():
        raise SystemExit("no-replace report exists")
    try:
        arms = {"A": inspect("A",32), "B": inspect("B",64)}
        comparison = {stage: difference(arms["A"]["stages"][stage], arms["B"]["stages"][stage])
                      for stage in STAGES} if all(v["neutral_bitwise"] for v in arms.values()) else {}
        report = {"schema": "c5-d2-op-v1", "status": "FIRST_DIFFERENCE_AT_ATTN_OUT" if
                  comparison and comparison["attn_norm"]["bitwise_equal"] and
                  not comparison["attn_out"]["bitwise_equal"] else "OBSERVER_OR_STAGE_GATE_FAILED",
                  "comparisons": comparison,
                  "arms": {name: {key: value for key, value in arm.items() if key != "stages"}
                           for name, arm in arms.items()}, "analyzer_sha256": sha(__file__)}
    except (EvidenceError, OSError, KeyError, TypeError, ValueError) as exc:
        report = {"schema": "c5-d2-op-v1", "status": "FAIL_EVIDENCE",
                  "reason": f"{type(exc).__name__}: {exc}"}
    write_new(OUT, report)
    print(json.dumps({"status": report["status"], "reason": report.get("reason")}))
    return 0 if report["status"] == "FIRST_DIFFERENCE_AT_ATTN_OUT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
