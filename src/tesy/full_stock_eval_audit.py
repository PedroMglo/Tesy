"""Independent stock-only run audit; never infers Tesy performance."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

MODEL_SHA = "52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4"
MODEL_BYTES = 12109564352
WORKLOADS = {"extraction-long": 302, "code-short": 132}


def upper_median_p95(values: list[float]) -> dict:
    if len(values) != 5 or any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("expected five finite nonnegative independent runs")
    ordered = sorted(values)
    return {
        "median": ordered[len(ordered) // 2],
        "p95": ordered[math.ceil(0.95 * len(ordered)) - 1],
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def resource_peaks(rows: list[dict]) -> dict:
    if not rows or any(row.get("gpu", {}).get("status") != "OK" for row in rows):
        raise ValueError("GPU telemetry incomplete")
    valid = [row for row in rows if set(row.get("process", {})) == {
        "VmRSS_bytes", "VmSwap_bytes"
    }]
    if not valid or any(row["process"]["VmSwap_bytes"] != 0 for row in valid):
        raise ValueError("missing process telemetry or swap")
    for row in rows:
        gpu = row["gpu"]
        for key in ("memory_used_bytes", "temperature_c", "power_w"):
            value = gpu.get(key)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid GPU telemetry {key}")
    return {
        "valid_process_samples": len(valid),
        "terminal_samples_without_process": len(rows) - len(valid),
        "peak_process_rss_bytes": max(row["process"]["VmRSS_bytes"] for row in valid),
        "peak_process_swap_bytes": 0,
        "peak_gpu_used_bytes": max(row["gpu"]["memory_used_bytes"] for row in rows),
        "peak_gpu_temperature_c": max(row["gpu"]["temperature_c"] for row in rows),
        "peak_gpu_power_w": max(row["gpu"]["power_w"] for row in rows),
    }


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def audit_run(root: Path, *, workload: str, ngl: int, rep: int) -> dict:
    if (root / "failure.json").exists():
        raise ValueError(f"failed root: {root}")
    model = _load(root / "model.json")
    doctor = _load(root / "doctor.json")
    capacity = _load(root / "placement-capacity.json")
    provenance = _load(root / "runtime-provenance.json")
    run = _load(root / "run.json")
    rows = [
        json.loads(line)
        for line in (root / "resources.jsonl").read_text().splitlines()
        if line
    ]

    _require(model["status"] == "PASS", "model identity failed")
    _require(model["observed"]["sha256"] == MODEL_SHA, "model SHA mismatch")
    _require(model["observed"]["size_bytes"] == MODEL_BYTES, "model size mismatch")
    _require(doctor["reference_check"]["status"] == "PASS", "host profile failed")
    _require(doctor["snapshot"]["virtualization"]["status"] == "PHYSICAL",
             "not physical host")
    _require(capacity["admitted"] is True, "placement not admitted")
    _require(capacity["placement_id"] == f"stock-chat-ngl-{ngl}",
             "placement identity mismatch")
    _require(provenance["schema"] == "tesy.full_model_stock_server_runtime_provenance.v1",
             "runtime provenance schema mismatch")
    _require(provenance["status"] == "PASS", "runtime provenance failed")
    _require(provenance["argv"]["status"] == "PASS", "argv provenance failed")
    _require(len(provenance["ggml_cuda"]["mapped_matches"]) == 1,
             "CUDA mapping not unique")
    argv = provenance["argv"]["observed"]
    _require(argv[argv.index("--n-gpu-layers") + 1] == str(ngl), "ngl mismatch")
    _require("--reasoning-budget" in argv, "reasoning budget missing")
    _require(argv[argv.index("--reasoning-budget") + 1] == "0",
             "reasoning budget mismatch")
    _require(run["schema"] == "tesy.full_model_stock_chat_run.v1", "run schema")
    _require(run["prompt_file"] == f"benchmarks/prompts/vertical-eval-{workload}.txt",
             "prompt identity mismatch")
    _require(run["max_tokens"] == 128, "output budget mismatch")
    _require(run["finish_reason"] in {"stop", "length"}, "invalid finish reason")
    _require(run["usage"]["prompt_tokens"] == WORKLOADS[workload],
             "prompt token count mismatch")
    _require(1 <= run["usage"]["completion_tokens"] <= 128,
             "completion count out of range")
    _require(run["timings"]["predicted_n"] == run["usage"]["completion_tokens"],
             "backend/usage completion counts differ")
    _require(run["timings"]["prompt_n"] == WORKLOADS[workload],
             "backend prompt token count mismatch")
    _require(run["timings"]["cache_n"] == 0, "unexpected prompt cache")
    _require(bool(run["output_text"]), "empty output")
    for key in ("server_launch_to_health_s", "ttft_s", "generation_request_s"):
        value = run[key]
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"invalid timing {key}")
    _require(run["ttft_s"] <= run["generation_request_s"], "TTFT exceeds request")
    _require((root / "stream.sse").is_file(), "missing raw SSE")
    _require((root / "sse-events.jsonl").is_file(), "missing event trace")
    resource = resource_peaks(rows)
    return {
        "root": str(root),
        "rep": rep,
        "workload": workload,
        "n_gpu_layers": ngl,
        "prompt_tokens": run["usage"]["prompt_tokens"],
        "output_tokens": run["usage"]["completion_tokens"],
        "finish_reason": run["finish_reason"],
        "output_sha256": hashlib.sha256(run["output_text"].encode()).hexdigest(),
        "server_launch_to_health_s": run["server_launch_to_health_s"],
        "ttft_s": run["ttft_s"],
        "generation_request_s": run["generation_request_s"],
        "backend_predicted_per_token_ms": run["timings"]["predicted_per_token_ms"],
        "runtime_executable_sha256": provenance["executable"]["sha256"],
        "runtime_cuda_sha256": provenance["ggml_cuda"]["sha256"],
        "resources": resource,
    }


def audit_group(root: Path) -> dict:
    runs = []
    for rep in range(1, 6):
        for workload in WORKLOADS:
            for ngl in (0, 12):
                run_root = root / f"rep{rep}-{workload}-ngl{ngl}"
                runs.append(audit_run(run_root, workload=workload, ngl=ngl, rep=rep))
    expected_dirs = {Path(run["root"]).name for run in runs}
    actual_dirs = {path.name for path in root.iterdir() if path.is_dir()}
    if actual_dirs != expected_dirs:
        raise ValueError("unexpected or missing evaluation root")
    if len({r["runtime_executable_sha256"] for r in runs}) != 1:
        raise ValueError("stock executable changed during campaign")
    if len({r["runtime_cuda_sha256"] for r in runs}) != 1:
        raise ValueError("CUDA backend changed during campaign")
    aggregate = []
    for workload in WORKLOADS:
        for ngl in (0, 12):
            selected = [r for r in runs if r["workload"] == workload and r["n_gpu_layers"] == ngl]
            aggregate.append({
                "workload": workload,
                "n_gpu_layers": ngl,
                "output_tokens": sorted(set(r["output_tokens"] for r in selected)),
                "finish_reasons": sorted(set(r["finish_reason"] for r in selected)),
                "output_sha256s": sorted(set(r["output_sha256"] for r in selected)),
                "server_launch_to_health_s": upper_median_p95([
                    r["server_launch_to_health_s"] for r in selected
                ]),
                "ttft_s": upper_median_p95([r["ttft_s"] for r in selected]),
                "generation_request_s": upper_median_p95([
                    r["generation_request_s"] for r in selected
                ]),
                "backend_predicted_per_token_ms": upper_median_p95([
                    r["backend_predicted_per_token_ms"] for r in selected
                ]),
            })
    return {
        "schema": "tesy.full_stock_chat_eval_summary.v1",
        "status": "PASS",
        "classification": "MEASURED_STOCK_ONLY_NOT_TESY_COMPARISON",
        "group_root": str(root),
        "n_runs": len(runs),
        "runs": runs,
        "aggregate": aggregate,
        "pending_external_audit": True,
        "claim_boundary": "Stock-only baseline; no causal Tesy performance comparison.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("group", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audit_group(args.group)
    with args.output.open("x") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    main()
