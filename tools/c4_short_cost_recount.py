#!/usr/bin/env python3
"""Descriptive C4 short-run counters; never an acceptance/timing analyzer."""

import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/c4-p1-ub64-short-cost-recount01.json"
RUNS = ("c4-q0-short-off01", "c4-p1-ub64-short01")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def one(run):
    stem = ROOT / "results" / run
    log_path = Path(str(stem) + ".stderr")
    manifest_path = Path(str(stem) + ".json")
    log = log_path.read_text()
    manifest = json.loads(manifest_path.read_text())
    section = log.split("C4_STATS_BEGIN latency-short\n", 1)[1].split(
        "\nC4_STATS_END latency-short", 1)[0]
    patterns = {
        "remap_calls": r"remap calls = (\d+)",
        "expert_hits": r"expert hits = (\d+)",
        "expert_misses": r"misses = (\d+)",
        "cold_misses": r"misses = \d+ \((\d+) cold\)",
        "graph_wave_callbacks": r"waves = (\d+)",
        "nonempty_wave_callbacks": r"waves = \d+ \((\d+) non-empty\)",
        "preloads_issued": r"preloads issued = (\d+)",
        "wave_wait_ms_accumulated": r"wave stall = ([0-9.]+) ms",
    }
    result = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, section)
        if not match:
            raise ValueError(f"{run}: missing {key}")
        result[key] = float(match.group(1)) if key.endswith("accumulated") else int(match.group(1))
    if manifest["returncode"] != 0 or manifest["stop_reason"] is not None:
        raise ValueError(f"{run}: run did not terminate normally")
    result["process_read_bytes_last_sample"] = manifest["last_sample"]["proc"]["read_bytes"]
    result["cgroup_peak_bytes"] = manifest["maxima"]["cgroup_peak_bytes"]
    result["gpu_used_mib_max"] = manifest["maxima"]["gpu_used_mib"]
    result["source_sha256"] = {p.name: sha(p) for p in (log_path, manifest_path)}
    return result


def main():
    if OUT.exists():
        raise SystemExit("no-replace output exists")
    rows = {run: one(run) for run in RUNS}
    old, new = (rows[run] for run in RUNS)
    deltas = {
        key: {"absolute": new[key] - old[key],
              "relative_pct": 100 * (new[key] / old[key] - 1)}
        for key in ("expert_misses", "graph_wave_callbacks",
                    "wave_wait_ms_accumulated", "process_read_bytes_last_sample")
    }
    result = {
        "schema": "c4-short-cost-recount-v1",
        "status": "DESCRIPTIVE_ONLY_NUMERIC_GATE_FAILED",
        "scope": "single 113-ID fresh-process runs with unchanged external batch 256",
        "units": {"wave_wait_ms_accumulated": "overlapping backend wait, not exclusive wall",
                  "process_read_bytes_last_sample": "/proc process accounting, not physical NVMe traffic"},
        "runs": rows,
        "candidate_minus_control": deltas,
        "limitations": ["ub64 routed inputs and expert sets differ numerically",
                        "one run per arm; no matched timing confirmation",
                        "source stderr and manifest hashes are post-run seals"],
        "analyzer_sha256": sha(Path(__file__)),
    }
    with OUT.open("x") as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({key: value["relative_pct"] for key, value in deltas.items()}))


if __name__ == "__main__":
    main()
