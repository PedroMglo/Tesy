#!/usr/bin/env python3
"""Run one canonical GPT-OSS layer at a time in separate bounded scopes."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


MODEL = "/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf"
WORKLOAD = "results/c2-target-numeric-v1.ids"
EXPECTED_PHASES = ["prefill0", "prefill128", "prefill_final",
                   "decode0", "decode1", "decode7", "decode31"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case", choices=("log", "spec"))
    ap.add_argument("--attempt", choices=("01", "02"), default="02")
    args = ap.parse_args()
    capture_stem = Path(f"results/c3-r2-broad-{args.case}01")
    capture_root = Path(str(capture_stem) + ".raw")
    summary_path = Path(f"results/c3-r2-broad-{args.case}-reference-summary{args.attempt}.json")
    if summary_path.exists():
        raise SystemExit(f"no-replace output exists: {summary_path}")
    capture_manifest = json.loads(Path(str(capture_stem)+".json").read_text())
    if capture_manifest["returncode"] != 0 or capture_manifest["stop_reason"] is not None:
        raise SystemExit("source capture failed")
    if (capture_root / "phases.txt").read_text().splitlines() != EXPECTED_PHASES:
        raise SystemExit("source phase schedule changed")
    results = []
    status = "PASS"
    reason = None
    for layer in range(36):
        device = "cpu" if layer < 29 else "gpu"
        run_id = f"c3-r2-broad-{args.case}-ref-l{layer:02d}-{args.attempt}"
        command = ["systemd-run", "--user", "--scope", "--property=MemoryMax=18G",
                   "--property=MemorySwapMax=0", "python3", "tools/run_bounded.py",
                   "--run-id", run_id, "--model-id", "gpt-oss-120b-mxfp4-gguf",
                   "--backend", "streaming", "--variant", f"c3-canonical-layer{layer}-{device}",
                   "--workload", WORKLOAD, "--cache-condition",
                   "capture-complete-page-cache-uncontrolled", "--timeout-s", "180",
                   "--max-rss-gib", "17", "--min-available-gib", "6",
                   "--max-gpu-mib", "7000", "--max-cpu-c", "95",
                   "--max-gpu-c", "80", "--max-nvme-c", "70", "--require-telemetry",
                   "--", "tools/c3_layer_reference", MODEL, str(capture_root),
                   str(layer), device]
        proc = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=False)
        print(f"layer={layer} device={device} exit={proc.returncode}", flush=True)
        if proc.returncode != 0:
            status = "FAIL_RUN"
            reason = f"{run_id}: {proc.stderr[-500:]} {proc.stdout[-500:]}"
            break
        manifest_path = Path(f"results/{run_id}.json")
        stdout_path = Path(f"results/{run_id}.stdout")
        try:
            manifest = json.loads(manifest_path.read_text())
            result = json.loads(stdout_path.read_text().strip())
            if manifest["returncode"] != 0 or manifest["stop_reason"] is not None or \
               manifest["cgroup_end"]["swap_current"] != 0 or \
               len(result["rows"]) != 7 or not result["all_bitwise"] or \
               [r["phase"] for r in result["rows"]] != EXPECTED_PHASES or \
               result["layer"] != layer or result["device"] != device:
                raise ValueError("manifest/reference row failed")
            for group in ("events", "events_local"):
                for event in ("max", "oom", "oom_kill"):
                    if manifest["cgroup_start"][group][event] != \
                       manifest["cgroup_end"][group][event]:
                        raise ValueError(f"cgroup {group}/{event} changed")
            results.append({"layer":layer,"device":device,
                            "run_id":run_id,"manifest_sha256":sha(manifest_path),
                            "stdout_sha256":sha(stdout_path),
                            "cgroup_peak_bytes":manifest["cgroup_end"]["memory_peak"],
                            "rows":result["rows"]})
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            status = "FAIL_EVIDENCE"
            reason = f"{run_id}: {exc}"
            break
    report = {"schema":"c3-all-layer-reference-v1","status":status,
              "case":args.case,"capture_run_id":capture_stem.name,
              "capture_manifest_sha256":sha(str(capture_stem)+".json"),
              "capture_index_sha256":sha(capture_root/"index.tsv"),
              "capture_phases_sha256":sha(capture_root/"phases.txt"),
              "reference_binary_sha256":sha("tools/c3_layer_reference"),
              "layers_completed":len(results),"comparisons":sum(len(x["rows"]) for x in results),
              "reason":reason,"layers":results}
    with summary_path.open("x") as out:
        json.dump(report,out,indent=2,allow_nan=False)
        out.write("\n")
    print(f"{status}: {len(results)} layers, {report['comparisons']} comparisons", flush=True)
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
