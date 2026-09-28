#!/usr/bin/env python3
"""Run C48 canonical layers sequentially; stop and preserve the first failure."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from c2_gate import GateError, strict_json
from c3_compare_capture_logits import resources
from c7_boundary_gate import capture

MODEL = "/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf"
BACKEND = "/tmp/tesy-c48-backend-20260928"
WITNESS = [25, 26, 27, 28, 24, 29]
PHASES = ["prefill0", "prefill128", "prefill_final", "decode0", "decode1", "decode7", "decode31"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_stat():
    st = Path(MODEL).stat()
    return {"dev": st.st_dev, "inode": st.st_ino, "size_bytes": st.st_size,
            "mtime_ns": st.st_mtime_ns, "ctime_ns": st.st_ctime_ns}


def cool_start(root):
    for attempt in range(25):
        available = next(int(line.split()[1])*1024 for line in Path("/proc/meminfo").read_text().splitlines()
                         if line.startswith("MemAvailable:"))
        if available < 6*2**30 or shutil.disk_usage(root).free < 20*2**30:
            raise GateError("host RAM/disk precondition failed")
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,temperature.gpu",
             "--format=csv,noheader,nounits"], text=True, timeout=10).strip()
        gpu_used, gpu_c = [float(x.strip()) for x in output.split(",")]
        sensors = json.loads(subprocess.check_output(["sensors", "-j"], text=True, timeout=10))
        cpu_c = float(sensors["k10temp-pci-00c3"]["Tctl"]["temp1_input"])
        nvme_c = float(sensors["nvme-pci-c100"]["Composite"]["temp1_input"])
        if gpu_used > 500:
            raise GateError("GPU no longer idle before reference")
        state = {"mem_available_bytes": available, "gpu_idle_mib": gpu_used,
                 "gpu_c": gpu_c, "cpu_c": cpu_c, "nvme_c": nvme_c}
        if cpu_c <= 75 and gpu_c <= 60 and nvme_c <= 60:
            return state
        print("thermal_recovery", attempt + 1, state, flush=True)
        time.sleep(5)
    raise GateError("thermal recovery precondition timed out at 120 s")


def validate_result(result, layer, device):
    if result["schema"] != "c48-p12-layer-reference-v1" or result["layer"] != layer or \
       result["device"] != device or result["canonical_layer_bytes"] != 1697956352 or \
       [r["phase"] for r in result["rows"]] != PHASES or \
       result["numeric_rows"] != (5 if layer == 35 else 7) or \
       result["masked_rows"] != (2 if layer == 35 else 0):
        raise GateError("canonical row schema/count/placement invalid")
    for row in result["rows"]:
        if row["state"] == "N/A_MASKED":
            if layer != 35 or row["phase"] not in ("prefill0", "prefill128"):
                raise GateError("unexpected masked reference row")
            continue
        if row["state"] != "NUMERIC" or not row["routing_ids_equal"] or \
           not row["routing_weights_bitwise"] or not row["ffn_bitwise"] or \
           row["routing_weights_nonfinite"] or row["ffn_nonfinite"]:
            return False
    return bool(result["all_bitwise"])


def one(root, layer, commit):
    raw = root / "raw"
    device = "cpu" if layer < 25 else "gpu"
    run_id = f"c48-ref-p12-l{layer:02d}-01"
    stem = raw / run_id
    if any(Path(str(stem)+suffix).exists() for suffix in (".json", ".stdout", ".stderr", ".samples.jsonl")):
        raise GateError("no-replace reference run exists")
    protocol = strict_json((root/"reference-protocol.json").read_text())
    if model_stat() != protocol["model_stat"]:
        raise GateError("model identity changed before reference")
    pre = cool_start(root)
    cmd = ["systemd-run", "--user", "--scope", "-p", "MemoryMax=19327352832",
           "-p", "MemorySwapMax=0", "--", "python3", "tools/run_bounded.py",
           "--run-id", run_id, "--model-id", "gpt-oss-120b-mxfp4-gguf",
           "--backend", "streaming", "--backend-root", BACKEND,
           "--output-root", str(raw.resolve()), "--variant", f"P12-canonical-layer{layer}-{device}",
           "--workload", "results/c2-target-numeric-v1.ids",
           "--cache-condition", "resident-canonical-one-layer-page-cache-uncontrolled",
           "--timeout-s", "180", "--max-rss-gib", "16", "--max-cgroup-gib", "16.5",
           "--min-available-gib", "6", "--max-gpu-mib", "6500", "--max-cpu-c", "100",
           "--max-gpu-c", "80", "--max-nvme-c", "70", "--require-telemetry", "--",
           "tools/c48_layer_reference", MODEL,
           str((raw/"c48-g2-p12-on01.capture").resolve()), str(layer), "--ngl", "12"]
    process = subprocess.run(cmd, text=True, capture_output=True, check=False)
    receipt = {"run_id": run_id, "layer": layer, "device": device,
               "measurement_commit": commit, "pre_run": pre, "scope_exit_code": process.returncode}
    manifest_path = Path(str(stem)+".json")
    if not manifest_path.is_file():
        return {**receipt, "status": "FAIL_RESOURCES_OR_EVIDENCE",
                "reason": "bounded manifest missing", "systemd_stderr_tail": process.stderr[-500:]}
    manifest = strict_json(manifest_path.read_text())
    receipt.update(raw_manifest_sha256=sha(manifest_path), elapsed_s=manifest.get("elapsed_s"),
                   maxima=manifest.get("maxima"), returncode=manifest.get("returncode"),
                   stop_reason=manifest.get("stop_reason"))
    if manifest.get("stop_reason") is not None or not manifest.get("mapped_libraries_match_ldd") or \
       manifest["artifact_identity"]["stat_at_launch"] != manifest["artifact_identity"]["stat_at_end"] or \
       manifest["artifact_identity"]["stat_at_launch"] != \
           strict_json((root/"reference-protocol.json").read_text())["model_stat"]:
        return {**receipt, "status": "FAIL_RESOURCES_OR_EVIDENCE",
                "reason": "bounded process or identity failed"}
    try:
        receipt["samples"] = resources(manifest, Path(str(stem)+".samples.jsonl")) if manifest["returncode"] == 0 else None
        stdout_path = Path(str(stem)+".stdout")
        result = strict_json(stdout_path.read_text())
        receipt["raw_stdout_sha256"] = sha(stdout_path)
        equal = validate_result(result, layer, device)
        receipt["rows"] = result["rows"]
        if not equal:
            return {**receipt, "status": "FAIL_SAME_PROFILE_FIDELITY", "reason": "canonical row differs"}
        if manifest["returncode"] != 0 or process.returncode != 0:
            raise GateError("reference process reported failure despite equal rows")
        return {**receipt, "status": "PASS", "numeric_rows": result["numeric_rows"],
                "masked_rows": result["masked_rows"]}
    except (OSError, KeyError, TypeError, ValueError, GateError) as exc:
        return {**receipt, "status": "FAIL_RESOURCES_OR_EVIDENCE",
                "reason": f"{type(exc).__name__}: {exc}"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("phase", choices=("witness", "remaining"))
    p.add_argument("measurement_commit")
    args = p.parse_args()
    root = args.root
    destination = root / ("reference-witness-summary.json" if args.phase == "witness"
                          else "reference-full-summary.json")
    if destination.exists():
        p.error("no-replace reference summary exists")
    protocol = strict_json((root/"reference-protocol.json").read_text())
    actual_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()
    if actual_commit != args.measurement_commit or dirty or \
       protocol["binary_sha256"] != sha("tools/c48_layer_reference") or \
       model_stat() != protocol["model_stat"]:
        p.error("reference identity differs from freeze")
    boundary = strict_json((root/"boundary-summary.json").read_text())
    if boundary["status"] != "SAME_PROFILE_BITWISE_PASS":
        p.error("observer boundary gate did not pass")
    _, coverage = capture(root/"raw/c48-g2-p12-on01.capture")
    if coverage["index_sha256"] != boundary["coverage"]["index_sha256"]:
        p.error("capture index differs from observer gate")
    if args.phase == "remaining":
        witness = strict_json((root/"reference-witness-summary.json").read_text())
        if witness["status"] != "PASS" or [x["layer"] for x in witness["layers"]] != WITNESS:
            p.error("witness reference gate did not pass")
    order = WITNESS if args.phase == "witness" else [i for i in range(36) if i not in WITNESS]
    report = {"schema": "c48-p12-reference-summary-v1", "phase": args.phase,
              "measurement_commit": args.measurement_commit,
              "protocol_sha256": sha(root/"reference-protocol.json"),
              "capture_index_sha256": coverage["index_sha256"],
              "status": "PASS", "layers": [], "numeric_rows": 0, "masked_rows": 0}
    for layer in order:
        try:
            row = one(root, layer, args.measurement_commit)
        except (OSError, ValueError, KeyError, TypeError, GateError,
                subprocess.SubprocessError) as exc:
            row = {"layer": layer, "status": "FAIL_RESOURCES_OR_EVIDENCE",
                   "reason": f"{type(exc).__name__}: {exc}"}
        report["layers"].append(row)
        print(f"layer={layer} status={row['status']} elapsed={row.get('elapsed_s')}", flush=True)
        if row["status"] != "PASS":
            report["status"] = row["status"]
            break
        report["numeric_rows"] += row["numeric_rows"]
        report["masked_rows"] += row["masked_rows"]
    with destination.open("x") as out:
        json.dump(report, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
