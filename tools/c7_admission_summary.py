#!/usr/bin/env python3
"""Compact, fail-closed G1 admission evidence from local raw manifests."""

import hashlib
import json
import re
from pathlib import Path

from c2_gate import GateError, strict_json
from c3_compare_capture_logits import resources


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path, obj):
    with path.open("x") as out:
        json.dump(obj, out, indent=2, sort_keys=True)
        out.write("\n")


def one(raw, profile, measurement_commit):
    stem = raw / f"c7-g1-{profile.lower()}-init01"
    manifest_path = Path(str(stem) + ".json")
    manifest = strict_json(manifest_path.read_text())
    sample_count = resources(manifest, Path(str(stem) + ".samples.jsonl"))
    if manifest["variant"] != profile + "-init-only" or manifest["returncode"] != 0:
        raise GateError("unexpected admission identity/status")
    if manifest["artifact_identity"]["stat_at_launch"] != manifest["artifact_identity"]["stat_at_end"]:
        raise GateError("model changed during admission")
    if manifest["mapped_backend_libraries_sha256"] != manifest["backend_libraries_sha256"] or not manifest["mapped_libraries_match_ldd"]:
        raise GateError("mapped backend library identity mismatch")
    for suffix, expected in manifest["output_sha256"].items():
        if sha(Path(str(stem) + suffix)) != expected:
            raise GateError("raw hash mismatch: " + suffix)
    log = Path(str(stem) + ".stderr").read_text()
    assigned = {int(layer): device for layer, device in re.findall(r"load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)", log)}
    if set(assigned) != set(range(37)):
        raise GateError("incomplete loader placement map")
    expected_first = 29 if profile == "P8" else 25
    if any(assigned[i] != ("CPU" if i < expected_first else "CUDA0") for i in range(37)):
        raise GateError("loader placement outside frozen profile")
    fields = {}
    for label, pattern in {
        "cpu_expert_pool_mib": r"CPU expert cache size =\s*([\d.]+) MiB",
        "gpu_expert_pool_mib": r"CUDA0 expert cache size =\s*([\d.]+) MiB",
        "gpu_model_buffer_mib": r"CUDA0 model buffer size =\s*([\d.]+) MiB",
        "cpu_pinned_model_buffer_mib": r"CUDA_Host model buffer size =\s*([\d.]+) MiB",
        "gpu_compute_buffer_mib": r"CUDA0 compute buffer size =\s*([\d.]+) MiB",
        "cpu_pinned_compute_buffer_mib": r"CUDA_Host compute buffer size =\s*([\d.]+) MiB",
    }.items():
        match = re.search(pattern, log)
        if match:
            fields[label] = float(match.group(1))
    return {
        "run_id": manifest["run_id"], "profile": profile,
        "measurement_commit": measurement_commit,
        "raw_manifest_sha256": sha(manifest_path),
        "raw_stem": str(stem),
        "started_utc": manifest["started_utc"], "ended_utc": manifest["ended_utc"],
        "elapsed_s": manifest["elapsed_s"], "returncode": manifest["returncode"],
        "stop_reason": manifest["stop_reason"], "samples": sample_count,
        "ready_elapsed_s": manifest["ready_elapsed_s"],
        "model_stat_unchanged": True, "mapped_libraries_verified": True,
        "mapped_backend_libraries_sha256": manifest["mapped_backend_libraries_sha256"],
        "loader_placement": {str(i): assigned[i] for i in range(37)},
        "output_on_gpu": assigned[36] == "CUDA0",
        "maxima": manifest["maxima"],
        "cgroup_end_peak_bytes": manifest["cgroup_end"]["memory_peak"],
        "cgroup_end_swap_bytes": manifest["cgroup_end"]["swap_current"],
        "cgroup_events_unchanged": manifest["cgroup_start"]["events"] == manifest["cgroup_end"]["events"],
        "loader_reported": fields,
        "scope_memory_max_bytes": manifest["cgroup_start"]["memory_max"],
        "scope_swap_max_bytes": manifest["cgroup_start"]["swap_max"],
    }


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("measurement_commit")
    args = p.parse_args()
    root = args.root
    raw = root / "raw"
    preflight = strict_json((raw / "preflight.json").read_text())
    if preflight["measurement_commit"] != args.measurement_commit or not preflight["worktree_clean"]:
        raise GateError("preflight measurement identity invalid")
    rows = [one(raw, p, args.measurement_commit) for p in ("P8", "P12")]
    write_new(root / "preflight.json", {**preflight, "raw_sha256": sha(raw / "preflight.json")})
    write_new(root / "admission.json", {
        "schema": "c7-g1-admission-v1", "measurement_commit": args.measurement_commit,
        "status": "INIT_ONLY_ADMITTED_FORWARD_UNKNOWN",
        "profiles": rows,
        "reserve_mib": {"P8": 6500 - rows[0]["maxima"]["gpu_used_mib"],
                        "P12": 6500 - rows[1]["maxima"]["gpu_used_mib"]},
        "limitation": "expert pools are lazily committed; forward workspace and CPU pool residency are not bounded by init-only peaks",
        "next_gate": "bounded P12 minimum forward under E18 before any long workload",
    })
    with (root / "runs.jsonl").open("x") as out:
        for row in rows:
            out.write(json.dumps({k: row[k] for k in (
                "run_id", "profile", "measurement_commit", "raw_manifest_sha256", "raw_stem",
                "started_utc", "ended_utc", "elapsed_s", "returncode", "stop_reason",
                "maxima", "samples")}, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
