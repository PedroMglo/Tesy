#!/usr/bin/env python3
"""Compact, scoped extraction from the one C4 Nsight short diagnostic."""

import hashlib
import json
from pathlib import Path
import sqlite3

from c2_gate import strict_json
from c3_compare_capture_logits import resources

ROOT = Path(__file__).resolve().parents[1]
STEM = ROOT / "results/c4-p0-nsys-short-off01"
BRIDGE = ROOT / "results/c4-q0-short-off01.f32"
OUT = ROOT / "results/c4-p0-nsys-summary01.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate(conn, table):
    count, duration = conn.execute(f"select count(*),coalesce(sum(end-start),0) from {table}").fetchone()
    return {"events": count, "summed_duration_s": duration / 1e9}


def main():
    if OUT.exists():
        raise SystemExit("no-replace output exists")
    manifest_path = Path(str(STEM) + ".json")
    manifest = strict_json(manifest_path.read_text())
    sample_path = Path(str(STEM) + ".samples.jsonl")
    n_samples = resources(manifest, sample_path)
    f32_path = Path(str(STEM) + ".f32")
    if f32_path.stat().st_size != 201088 * 4 or f32_path.read_bytes() != BRIDGE.read_bytes():
        raise ValueError("Nsight run final logits differ from unprofiled bridge")
    case_lines = Path(str(STEM) + ".cases.tsv").read_text().splitlines()
    if len(case_lines) != 2 or not case_lines[1].startswith("latency-short\t113\t"):
        raise ValueError("profiled prompt schedule invalid")
    completion_s = float(case_lines[1].split("\t")[3])
    if completion_s <= 0:
        raise ValueError("invalid completed prefill time")
    db = Path(str(STEM) + ".sqlite")
    with sqlite3.connect(db) as conn:
        tables = {name for (name,) in conn.execute("select name from sqlite_master where type='table'")}
        required = {"CUPTI_ACTIVITY_KIND_KERNEL", "CUPTI_ACTIVITY_KIND_MEMCPY",
                    "CUPTI_ACTIVITY_KIND_MEMSET"}
        if not required <= tables:
            raise ValueError("Nsight CUDA activity tables missing")
        kernels = aggregate(conn, "CUPTI_ACTIVITY_KIND_KERNEL")
        copies = aggregate(conn, "CUPTI_ACTIVITY_KIND_MEMCPY")
        sets = aggregate(conn, "CUPTI_ACTIVITY_KIND_MEMSET")
        h2d_count, h2d_bytes, h2d_ns = conn.execute(
            "select count(*),coalesce(sum(bytes),0),coalesce(sum(end-start),0) "
            "from CUPTI_ACTIVITY_KIND_MEMCPY where copyKind=1").fetchone()
        gpu_path = conn.execute("select min(start),max(end) from CUPTI_ACTIVITY_KIND_KERNEL").fetchone()
        if kernels["events"] == 0 or h2d_count == 0 or gpu_path[0] is None:
            raise ValueError("CUDA kernel/H2D timeline unavailable")
    result = {"schema": "c4-p0-nsys-summary-v1",
              "status": "GPU_NODE_TIMELINE_AVAILABLE",
              "classification": "Nsight diagnostic on physical target; profiled wall is not production timing",
              "profiled_prefill_completion_s": completion_s,
              "resource_samples": n_samples,
              "gpu_kernel": kernels, "gpu_memcpy": copies, "gpu_memset": sets,
              "h2d_cuda_payload": {"events": h2d_count, "bytes": h2d_bytes,
                                   "summed_duration_s": h2d_ns / 1e9},
              "gpu_kernel_event_span_s": (gpu_path[1] - gpu_path[0]) / 1e9,
              "limitations": ["CUPTI event duration sums overlap and are not exclusive critical time",
                              "trace covers GPU events, not CPU GEMM, expert reads or host scheduler cost",
                              "CUDA memcpy payload is not a measured physical PCIe byte count",
                              "Nsight node-level overhead cannot be used as a speed comparison"],
              "source_sha256": {str(path.relative_to(ROOT)): sha(path) for path in
                                (manifest_path, sample_path, f32_path, BRIDGE,
                                 Path(str(STEM) + ".nsys-rep"), db)},
              "analyzer_sha256": sha(Path(__file__))}
    with OUT.open("x") as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"status": result["status"], "kernels": kernels,
                      "memcpy": copies, "h2d_cuda_payload": result["h2d_cuda_payload"]}))


if __name__ == "__main__":
    main()
