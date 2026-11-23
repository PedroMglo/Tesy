#!/usr/bin/env python3
"""Count routed and parked pairs in existing C3 representative microbatches."""

import csv
import hashlib
import json
import math
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "results/c3-r2-broad-spec01.raw"
OUT = ROOT / "results/c4-p0-capture-recount01.json"
C = 14
K = 4
EXPERTS = 128


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def values(root, row, expected, fmt):
    shape = [int(x) for x in row["ne"].split(",")]
    stride = [int(x) for x in row["nb"].split(",")]
    if len(shape) != 4 or len(stride) != 4 or shape[:2] != expected:
        raise ValueError("capture shape/stride mismatch")
    payload = (root / row["file"]).read_bytes()
    if len(payload) != int(row["bytes"]):
        raise ValueError("capture byte count mismatch")
    size = struct.calcsize(fmt)
    result = []
    for t in range(shape[1]):
        for k in range(shape[0]):
            offset = t * stride[1] + k * stride[0]
            if offset + size > len(payload):
                raise ValueError("capture stride out of bounds")
            result.append(struct.unpack_from(fmt, payload, offset)[0])
    return result


def main():
    if OUT.exists():
        raise SystemExit("no-replace output exists")
    index = CAPTURE / "index.tsv"
    records = list(csv.DictReader(index.open(), delimiter="\t"))
    if not records or set(records[0]) != {"phase", "layer", "name", "type", "ne", "nb", "bytes", "file"}:
        raise ValueError("capture index schema mismatch")
    phases = ["prefill0", "prefill128", "prefill_final", "decode0", "decode1", "decode7", "decode31"]
    rows = []
    for phase in phases:
        for layer in range(36):
            selected = [row for row in records if row["phase"] == phase and int(row["layer"]) == layer]
            route = [row for row in selected if row["name"] == "ffn_moe_topk"]
            if len(route) != 1 or route[0]["type"] != "i32":
                raise ValueError(f"missing route {phase}/{layer}")
            n = int(route[0]["ne"].split(",")[1])
            logical = values(CAPTURE, route[0], [K, n], "<i")
            if any(value < 0 or value >= EXPERTS for value in logical):
                raise ValueError("invalid logical expert ID")
            unique = len(set(logical))
            masks = [row for row in selected if row["name"] == "ffn_moe_wave_mask"]
            expected_waves = (min(EXPERTS, n * K) + C - 1) // C if n * K > 32 else 1
            if len(masks) != (expected_waves if expected_waves > 1 else 0):
                raise ValueError(f"graph wave count changed {phase}/{layer}")
            if masks:
                active = []
                for row in masks:
                    if row["type"] != "f32" or row["ne"].split(",")[:3] != ["1", str(K), str(n)]:
                        raise ValueError("mask shape mismatch")
                    payload = (CAPTURE / row["file"]).read_bytes()
                    if len(payload) != int(row["bytes"]):
                        raise ValueError("mask byte count mismatch")
                    ne = [int(x) for x in row["ne"].split(",")]
                    nb = [int(x) for x in row["nb"].split(",")]
                    mask = []
                    for token in range(n):
                        for k in range(K):
                            offset = token * nb[2] + k * nb[1]
                            if offset + 4 > len(payload):
                                raise ValueError("mask stride out of bounds")
                            value = struct.unpack_from("<f", payload, offset)[0]
                            if not math.isfinite(value) or value not in (0.0, 1.0):
                                raise ValueError("nonbinary wave mask")
                            mask.append(int(value))
                    active.append(mask)
                if any(sum(mask[i] for mask in active) != 1 for i in range(n * K)):
                    raise ValueError("each routed pair must belong to one wave")
                active_per_wave = [sum(mask) for mask in active]
                if sum(x > 0 for x in active_per_wave) != (unique + C - 1) // C:
                    raise ValueError("active wave count disagrees with unique experts")
            else:
                active_per_wave = [n * K]
            graph_waves = len(active_per_wave)
            rows.append({"phase": phase, "layer": layer, "n_tokens": n,
                         "logical_top_k": K, "unique_experts": unique,
                         "graph_waves": graph_waves,
                         "plan_waves": sum(x > 0 for x in active_per_wave),
                         "empty_waves": sum(x == 0 for x in active_per_wave),
                         "active_pairs_per_wave": active_per_wave,
                         "useful_pairs": n * K,
                         "parking_pair_positions": n * K * (graph_waves - 1)})
    result = {"schema": "c4-p0-capture-recount-v1",
              "classification": "reanalysis of C3 model capture at representative real microbatches; no new physical run",
              "rows": rows,
              "limitations": ["mask positions are not executed kernels or measured FLOPs",
                              "captured microbatches are selected states, not all production microbatches",
                              "last layer requests only one output token and uses a different shape"],
              "source_sha256": {"index": sha(index), "capture_manifest": sha(ROOT / "results/c3-r2-broad-spec01.json")},
              "analyzer_sha256": sha(Path(__file__))}
    with OUT.open("x") as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write("\n")
    for phase in phases[:3]:
        selected = [row for row in rows if row["phase"] == phase]
        print(phase, "layers", len(selected), "unique_minmax",
              min(row["unique_experts"] for row in selected),
              max(row["unique_experts"] for row in selected),
              "empty_waves", sum(row["empty_waves"] for row in selected))


if __name__ == "__main__":
    main()
