#!/usr/bin/env python3
"""Recount C3 wave callbacks and static pair positions without timing claims."""

import hashlib
import json
from pathlib import Path

from c3_analyze_prefill import stats

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/c3-p1-prefill-all-off01.stderr"
SUMMARY = ROOT / "results/c3-p1-summary01.json"
OUT = ROOT / "results/c4-p0-source-recount01.json"
E, K, S = 128, 4, 32
C = (S - K) // 2
LENGTHS = {"latency-short": 113, "latency-medium": 496, "latency-long": 1522}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def shapes(n, ubatch):
    # External batches are 256 IDs; both tested ubatch sizes divide 256.
    result = []
    for external in range(0, n, 256):
        count = min(256, n - external)
        for offset in range(0, count, ubatch):
            result.append(min(ubatch, count - offset))
    return result


def static(n, ubatch):
    sizes = shapes(n, ubatch)
    waves = [(min(E, size * K) + C - 1) // C if size * K > S else 1
             for size in sizes]
    pairs = sum(size * K * wave for size, wave in zip(sizes, waves))
    useful = n * K
    return {"microbatch_tokens": sizes, "graph_waves_per_layer": sum(waves),
            "logical_pairs_per_layer": useful, "graph_pair_positions_per_layer": pairs,
            "parking_pair_positions_per_layer": pairs - useful}


def main():
    if OUT.exists():
        raise SystemExit("no-replace output exists")
    rows = stats(str(SOURCE))
    summary = json.loads(SUMMARY.read_text())
    by_name = {entry["case"]: entry for entry in summary["cases"]}
    result = {"schema": "c4-p0-source-recount-v1",
              "classification": "C3 backend counters measured; graph pair positions source/static only",
              "constants": {"experts": E, "top_k": K, "slots": S, "wave_capacity": C},
              "cases": {},
              "limitations": ["graph pair positions are not measured FLOPs, executed kernels or critical time",
                              "wave stall is overlapping accumulated backend wait",
                              "pread returned bytes are application payload, not device-exclusive NVMe traffic"],
              "source_sha256": {str(p.relative_to(ROOT)): sha(p) for p in (SOURCE, SUMMARY,
                  ROOT / "backends/streaming/src/llama-graph.cpp",
                  ROOT / "backends/streaming/src/llama-moe-stream.cpp")},
              "analyzer_sha256": sha(Path(__file__))}
    for name, n in LENGTHS.items():
        selected = [entry["counters"] for entry in rows if entry["case"] == name]
        if not selected:
            raise ValueError(f"missing C3 counters: {name}")
        wave_calls = sum(entry["wave_calls"] for entry in selected)
        nonempty = sum(entry["nonempty_waves"] for entry in selected)
        old = by_name[name]
        if sum(entry["misses"] for entry in selected) != old["backend_misses"]:
            raise ValueError("C3 miss count disagreement")
        ub32 = static(n, 32)
        if wave_calls != 35 * ub32["graph_waves_per_layer"]:
            raise ValueError("C3 wave callbacks disagree with 35 repeated graph paths")
        result["cases"][name] = {
            "prompt_ids": n, "c3_wave_callbacks": wave_calls,
            "c3_nonempty_wave_callbacks": nonempty,
            "c3_empty_wave_callbacks": wave_calls - nonempty,
            "c3_empty_callback_fraction": (wave_calls - nonempty) / wave_calls,
            "c3_misses": old["backend_misses"],
            "c3_wave_wait_s": old["backend_wave_stall_s"],
            "c3_pread_returned_bytes": old["read_returned_bytes"],
            "ub32_static": ub32, "ub64_static": static(n, 64)}
    with OUT.open("x") as out:
        json.dump(result, out, indent=2, allow_nan=False)
        out.write("\n")
    print(json.dumps({k: {"empty": v["c3_empty_wave_callbacks"],
                         "ub32_pairs": v["ub32_static"]["graph_pair_positions_per_layer"],
                         "ub64_pairs": v["ub64_static"]["graph_pair_positions_per_layer"]}
                      for k, v in result["cases"].items()}))


if __name__ == "__main__":
    main()
