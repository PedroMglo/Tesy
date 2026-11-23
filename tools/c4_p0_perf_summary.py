#!/usr/bin/env python3
"""Compact validation and CPU-cycle sample summary for the C4 short run."""

import hashlib
import json
from pathlib import Path
import re
import subprocess

from c2_gate import strict_json
from c3_compare_capture_logits import resources

ROOT = Path(__file__).resolve().parents[1]
STEM = ROOT / "results/c4-p0-perf-short-off01"
BRIDGE = ROOT / "results/c4-q0-short-off01.f32"
OUT = ROOT / "results/c4-p0-perf-summary02.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUT.exists():
        raise SystemExit("no-replace output exists")
    manifest_path = Path(str(STEM) + ".json")
    manifest = strict_json(manifest_path.read_text())
    samples_path = Path(str(STEM) + ".samples.jsonl")
    n_samples = resources(manifest, samples_path)
    f32 = Path(str(STEM) + ".f32")
    if f32.stat().st_size != 201088 * 4 or f32.read_bytes() != BRIDGE.read_bytes():
        raise ValueError("perf run final logits differ from unprofiled bridge")
    case_lines = Path(str(STEM) + ".cases.tsv").read_text().splitlines()
    if len(case_lines) != 2 or not case_lines[1].startswith("latency-short\t113\t"):
        raise ValueError("profiled prompt schedule invalid")
    data = Path(str(STEM) + ".data")
    report = subprocess.check_output([
        "perf", "report", "-i", str(data), "--stdio", "--no-children", "-g", "none",
        "--sort", "dso,symbol", "-t", ";", "--percent-limit", "0.2"], text=True)
    lost = re.search(r"Total Lost Samples:\s*(\d+)", report)
    sample_count = re.search(r"Samples:\s*([\dKMG]+)\s+of event 'cycles:u'", report)
    if not lost or int(lost.group(1)) != 0 or not sample_count:
        raise ValueError("CPU profile missing or has lost samples")
    symbols = []
    for line in report.splitlines():
        match = re.match(r"\s*([\d.]+)%\s*;([^;]+);(.+)", line)
        if match:
            symbols.append({"sampled_cycle_share_pct": float(match.group(1)),
                            "shared_object": match.group(2).strip(),
                            "symbol": match.group(3).split(";", 1)[0].strip()})
    if not symbols or not any("ggml_vec_dot_mxfp4_q8_0" in x["symbol"] for x in symbols):
        raise ValueError("CPU symbols missing")
    result = {"schema": "c4-p0-perf-summary-v2",
              "status": "CPU_SAMPLES_AVAILABLE_OP_ATTRIBUTION_INCOMPLETE",
              "classification": "user cycles sampled on physical target; not critical-path wall fractions",
              "resource_samples": n_samples,
              "perf_event": "cycles:u", "sample_frequency_hz": 99,
              "lost_samples": 0,
              "top_flat_symbols": symbols[:12],
              "limitations": ["frame-pointer stack stops at ggml_graph_compute_thread for most vector-dot samples",
                              "MXFP4 vector dot may serve routed and non-routed matmuls; masked share is unknown",
                              "cycle sample percentages are not time saved by skipping parking pairs",
                              "perf overhead run is diagnostic, not a production timing arm"],
              "source_sha256": {str(path.relative_to(ROOT)): sha(path) for path in
                                (manifest_path, samples_path, f32, BRIDGE, data)},
              "analyzer_sha256": sha(Path(__file__))}
    with OUT.open("x") as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"status": result["status"], "top": symbols[:4]}))


if __name__ == "__main__":
    main()
