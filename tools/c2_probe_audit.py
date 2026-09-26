#!/usr/bin/env python3
"""Audit a bounded C2 multirow probe including resource and sample coverage."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from c2_gate import GateError, strict_json


ROOT = Path(__file__).resolve().parents[1]
VOCAB = 201088
ROW_BYTES = VOCAB * 4


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def audit(run_id, ids_path):
    stem = ROOT / "results" / run_id
    paths = {suffix: Path(str(stem) + suffix) for suffix in
             (".json", ".stderr", ".stdout", ".samples.jsonl", ".f32", ".rows.tsv")}
    manifest = strict_json(paths[".json"].read_text())
    samples = [strict_json(line) for line in paths[".samples.jsonl"].read_text().splitlines()]
    ids = [line.split("\t") for line in ids_path.read_text().splitlines()]
    if any(len(row) != 3 for row in ids):
        raise GateError("invalid token ID file")
    selected = manifest["command"][-1]
    cases = ids if selected == "all" else [row for row in ids if row[0] == selected]
    if not cases:
        raise GateError("selected case not in ID file")
    ubatch = int(manifest["command"][-2])
    expected_rows = sum(math.ceil(len(row[1].split(","))/ubatch) + len(row[2].split(","))
                        for row in cases)
    f32_size = paths[".f32"].stat().st_size if paths[".f32"].exists() else 0
    if f32_size % ROW_BYTES:
        raise GateError("partial float32 row detected")
    written_rows = f32_size // ROW_BYTES
    sample_ok = len(samples) >= 2
    sample_error = None
    if sample_ok:
        first = samples[0]
        start_path = manifest["cgroup_start"]["path"]
        pid = first.get("pid")
        sample_ok = (first["elapsed_s"] <= 2 and
                     0 <= manifest["elapsed_s"]-samples[-1]["elapsed_s"] <= 2 and
                     all(0 < b["elapsed_s"]-a["elapsed_s"] <= 3 for a,b in zip(samples,samples[1:])) and
                     all(x.get("pid") == pid and x.get("cgroup",{}).get("path") == start_path and
                         x.get("gpu") and x.get("thermal") and x.get("proc") and
                         x.get("mem_available_bytes") is not None for x in samples))
    if not sample_ok:
        sample_error = "missing/changed PID/cgroup/sensor or >3s telemetry gap/boundary"
    peak = manifest["maxima"].get("cgroup_peak_bytes")
    limits = manifest["limits"]
    initial = manifest["cgroup_start"]
    final = manifest["cgroup_end"]
    memory_max = initial["memory_max"]
    reclaim = limits["allow_cgroup_max_reclaim"]
    event_deltas = {name: final["events"].get(name,0)-initial["events"].get(name,0)
                    for name in ("max","oom","oom_kill")}
    local_deltas = {name: final["events_local"].get(name,0)-initial["events_local"].get(name,0)
                    for name in ("max","oom","oom_kill")}
    resources_ok = (sample_ok and manifest["cgroup_limit_enforced"] and
                    initial["swap_max"] == 0 and peak is not None and peak <= memory_max and
                    manifest["maxima"]["rss_bytes"] <= limits["max_rss_gib"]*2**30 and
                    manifest["maxima"]["gpu_used_mib"] <= limits["max_gpu_mib"] and
                    manifest["maxima"]["swap_bytes"] == 0 and final["swap_current"] == 0 and
                    all(event_deltas[k] == local_deltas[k] == 0 for k in ("oom","oom_kill")) and
                    (reclaim or event_deltas["max"] == local_deltas["max"] == 0) and
                    manifest["maxima"]["cpu_tctl_c"] <= limits["max_cpu_c"] and
                    manifest["maxima"]["gpu_temperature_c"] <= limits["max_gpu_c"] and
                    manifest["maxima"]["nvme_composite_c"] <= limits["max_nvme_c"] and
                    all(x["mem_available_bytes"] >= limits["min_available_gib"]*2**30 for x in samples))
    rows_index_present = paths[".rows.tsv"].exists()
    rows_index_count = len(paths[".rows.tsv"].read_text().splitlines())-1 if rows_index_present else None
    stderr = paths[".stderr"].read_text(errors="replace")
    backend_error = "C2_PROBE_ERROR:" in stderr or "CUDA error" in stderr
    complete = (manifest["returncode"] == 0 and manifest["stop_reason"] is None and
                rows_index_count == expected_rows == written_rows and not backend_error)
    hashes = {name:digest(path) for name,path in paths.items() if path.exists()}
    hashes["token_ids"] = digest(ids_path)
    report = {"schema_version":"c2-probe-audit-v1","run_id":run_id,
              "status":"PASS" if complete and resources_ok else "FAIL",
              "source_sha256":hashes,"expected_rows":expected_rows,"written_rows":written_rows,
              "row_index_count":rows_index_count,"sample_count":len(samples),
              "sample_ok":sample_ok,"sample_error":sample_error,"resources_ok":resources_ok,
              "stop_reason":manifest["stop_reason"],"returncode":manifest["returncode"],
              "cgroup_peak_bytes":peak,"cgroup_max_bytes":memory_max,
              "event_deltas":event_deltas,"local_event_deltas":local_deltas,
              "psi_full_total_delta_us":final["pressure"]["full"]["total"]-initial["pressure"]["full"]["total"],
              "maxima":manifest["maxima"],"backend_error":backend_error,
              "scope":"audit of one fixed-token probe; no free-generation quality or physical I/O attribution"}
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run_id")
    p.add_argument("--token-ids", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    result = audit(a.run_id, Path(a.token_ids))
    with Path(a.output).open("x") as out:
        json.dump(result, out, indent=2, allow_nan=False)
        out.write("\n")
    print(json.dumps({k:result[k] for k in ("run_id","status","expected_rows","written_rows",
                                               "resources_ok","stop_reason","event_deltas")}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
