#!/usr/bin/env python3
"""Fail-closed C4 exact-ID prompt and teacher-forced logits comparison."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

from c2_gate import GateError, strict_json
from c3_compare_capture_logits import resources

VOCAB = 201088
ROW_BYTES = VOCAB * 4
EXPECTED_ROWS = [
    "latency-long\t0\t1522",
    "latency-long-tf1-id16681\t1\t1523",
    "latency-long-tf2-id353\t2\t1524",
    "latency-long-tf3-id1302\t3\t1525",
    "latency-long-tf4-id2570\t4\t1526",
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def top_two(row):
    first = (-1, -math.inf)
    second = (-1, -math.inf)
    for i, (value,) in enumerate(struct.iter_unpack("<f", row)):
        if not math.isfinite(value):
            raise GateError(f"nonfinite logit at {i}")
        if value > first[1]:
            second, first = first, (i, value)
        elif value > second[1]:
            second = (i, value)
    if first[0] < 0 or second[0] < 0:
        raise GateError("short logits row")
    return {"top1_id": first[0], "top1_logit": first[1],
            "top2_id": second[0], "top2_logit": second[1],
            "margin": first[1] - second[1]}


def inspect(stem, arm):
    manifest_path = Path(str(stem) + ".json")
    manifest = strict_json(manifest_path.read_text())
    resources(manifest, Path(str(stem) + ".samples.jsonl"))
    env = manifest["explicit_env"]
    if arm == "off" and env.get("LLAMA_MOE_STREAM_NO_PRELOAD") != "1":
        raise GateError("OFF environment incorrect")
    if arm == "on" and "LLAMA_MOE_STREAM_NO_PRELOAD" in env:
        raise GateError("ON explicitly disables preload")
    rows_path = Path(str(stem) + ".rows.tsv")
    if rows_path.read_text().splitlines() != ["case\trow\ttokens", *EXPECTED_ROWS]:
        raise GateError("row schedule differs from frozen continuation")
    payload = Path(str(stem) + ".f32").read_bytes()
    if len(payload) != len(EXPECTED_ROWS) * ROW_BYTES:
        raise GateError("incomplete full logits vectors")
    row_summaries = [top_two(payload[i*ROW_BYTES:(i+1)*ROW_BYTES])
                     for i in range(len(EXPECTED_ROWS))]
    return manifest, payload, row_summaries, {
        "manifest_sha256": digest(manifest_path),
        "logits_sha256": hashlib.sha256(payload).hexdigest(),
        "rows_sha256": digest(rows_path),
        "samples_sha256": digest(Path(str(stem) + ".samples.jsonl")),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("off1", type=Path)
    parser.add_argument("off2", type=Path)
    parser.add_argument("on", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("no-replace output exists")
    try:
        inspected = [inspect(stem, arm) for stem, arm in
                     ((args.off1, "off"), (args.off2, "off"), (args.on, "on"))]
        manifests = [row[0] for row in inspected]
        for key in ("model_id", "model_path", "artifact_identity", "backend_sha",
                    "backend_libraries_sha256", "binary_sha256", "workload_sha256"):
            if any(manifest[key] != manifests[0][key] for manifest in manifests[1:]):
                raise GateError(f"provenance mismatch: {key}")
        if any(manifest["command"][:-2] != manifests[0]["command"][:-2] or
               manifest["command"][-1] != "long" for manifest in manifests):
            raise GateError("probe command differs beyond output path")
        first = inspected[0][1]
        mismatch = []
        for arm, result in zip(("off2", "on"), inspected[1:]):
            payload = result[1]
            for row in range(len(EXPECTED_ROWS)):
                left = first[row*ROW_BYTES:(row+1)*ROW_BYTES]
                right = payload[row*ROW_BYTES:(row+1)*ROW_BYTES]
                if left != right:
                    index = next(i for i in range(VOCAB)
                                 if left[i*4:(i+1)*4] != right[i*4:(i+1)*4])
                    mismatch.append({"arm": arm, "row": row, "first_logit_index": index})
        status = "CURRENT_PROFILE_PARITY_PASS" if not mismatch else "CURRENT_NUMERIC_DIVERGENCE"
        result = {"schema": "c4-q1-numeric-v1", "status": status,
                  "scope": "same fresh-process exact IDs, prompt end and four arbitrary teacher-forced positions; pre-sampler logits",
                  "rows": EXPECTED_ROWS, "mismatch": mismatch,
                  "top_two": {arm: row[2] for arm, row in zip(("off1", "off2", "on"), inspected)},
                  "sources": {arm: row[3] for arm, row in zip(("off1", "off2", "on"), inspected)},
                  "analyzer_sha256": digest(Path(__file__))}
    except (OSError, ValueError, KeyError, TypeError, GateError) as exc:
        result = {"schema": "c4-q1-numeric-v1", "status": "FAIL_EVIDENCE",
                  "reason": f"{type(exc).__name__}: {exc}"}
    with args.output.open("x") as out:
        json.dump(result, out, indent=2, allow_nan=False)
        out.write("\n")
    print(json.dumps({"status": result["status"], "mismatch": result.get("mismatch"),
                      "reason": result.get("reason")}))
    return 0 if result["status"] == "CURRENT_PROFILE_PARITY_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
