"""Read-only analysis of opt-in layer-2 numerical diagnostic F32 sidecars.

The arithmetic reconstructions are diagnostic. They never change the frozen
FFN/full-logit acceptance contract or select a different execution policy.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import struct
import sys
from array import array
from pathlib import Path

WIDTH = 2880
SLOTS = 4
STAGES = (
    "ffn_moe_up",
    "ffn_moe_up_biased",
    "ffn_moe_gate",
    "ffn_moe_gate_biased",
    "ffn_moe_swiglu_oai",
    "ffn_moe_down",
    "ffn_moe_down_biased",
    "ffn_moe_weighted",
)
ROUTE = (4, 0, 31, 17)
RESIDENT = frozenset((0, 1, 2, 3))


def read_f32(path: Path, count: int) -> array:
    if sys.byteorder != "little":
        raise ValueError("diagnostic F32 sidecars require little-endian host")
    raw = path.read_bytes()
    if len(raw) != count * 4:
        raise ValueError(f"{path}: expected {count * 4} bytes, got {len(raw)}")
    result = array("f")
    result.frombytes(raw)
    if not all(math.isfinite(x) for x in result):
        raise ValueError(f"{path}: non-finite F32 value")
    return result


def parity(reference: array, observed: array) -> dict[str, float | bool]:
    if len(reference) != len(observed) or not reference:
        raise ValueError("parity vectors must have equal nonzero length")
    max_abs = max(abs(float(a) - float(b)) for a, b in zip(reference, observed, strict=True))
    max_ref = max(abs(float(a)) for a in reference)
    dot = math.fsum(float(a) * float(b) for a, b in zip(reference, observed, strict=True))
    norm_a = math.fsum(float(a) * float(a) for a in reference)
    norm_b = math.fsum(float(b) * float(b) for b in observed)
    return {
        "max_abs": max_abs,
        "max_abs_ref": max_ref,
        "relative_max": max_abs / max(1.0, max_ref),
        "cosine": dot / max(1e-30, math.sqrt(norm_a * norm_b)),
        "bitwise": reference.tobytes() == observed.tobytes(),
    }


def f32_add(a: float, b: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(a) + float(b)))[0]


def sum_slots(weighted: array, slots: tuple[int, ...]) -> array:
    if len(weighted) != WIDTH * SLOTS or not slots:
        raise ValueError("weighted contributions or slot selection invalid")
    if any(slot not in range(SLOTS) for slot in slots):
        raise ValueError("slot out of range")
    result = array("f", weighted[slots[0] * WIDTH : (slots[0] + 1) * WIDTH])
    for slot in slots[1:]:
        offset = slot * WIDTH
        for i in range(WIDTH):
            result[i] = f32_add(result[i], weighted[offset + i])
    return result


def mixed_subset_sum(weighted: array, route: tuple[int, ...] = ROUTE) -> array:
    gpu_slots = tuple(i for i, expert in enumerate(route) if expert in RESIDENT)
    cpu_slots = tuple(i for i, expert in enumerate(route) if expert not in RESIDENT)
    if gpu_slots and cpu_slots:
        gpu = sum_slots(weighted, gpu_slots)
        cpu = sum_slots(weighted, cpu_slots)
        return array("f", (f32_add(g, c) for g, c in zip(gpu, cpu, strict=True)))
    return sum_slots(weighted, gpu_slots or cpu_slots)


def read_slot_mapping(log_path: Path) -> list[dict[str, int | float | str]]:
    pattern = re.compile(
        r"^vertical diagnostic slot=(\d+) expert=(\d+) backend=(CPU|GPU) "
        r"local=(\d+) local_id=(\d+) routing_weight=([^ ]+)$"
    )
    rows = []
    for line in log_path.read_text().splitlines():
        match = pattern.fullmatch(line)
        if match:
            slot, expert, backend, local, local_id, weight = match.groups()
            rows.append({
                "slot": int(slot), "expert": int(expert), "backend": backend,
                "local": int(local), "local_id": int(local_id),
                "routing_weight": float(weight),
            })
    if len(rows) != SLOTS or tuple(row["expert"] for row in rows) != ROUTE:
        raise ValueError("live slot mapping is missing or differs from frozen route")
    for row in rows:
        if (row["backend"] == "GPU") != (row["expert"] in RESIDENT):
            raise ValueError("live slot backend differs from frozen residency")
        if row["backend"] == "GPU" and row["local_id"] != row["expert"]:
            raise ValueError("GPU global/local mapping differs from resident identity")
        if not math.isfinite(row["routing_weight"]):
            raise ValueError("non-finite routing weight")
    return rows


def analyse(root: Path) -> dict:
    mapping = read_slot_mapping(root / "tool.stderr.txt")
    stages = {}
    first = [None] * SLOTS
    for stage in STAGES:
        stock = read_f32(root / f"layer2-stock-{stage}.f32", WIDTH * SLOTS)
        mixed = read_f32(root / f"layer2-mixed-{stage}.f32", WIDTH * SLOTS)
        per_slot = []
        for slot in range(SLOTS):
            lo = slot * WIDTH
            metrics = parity(
                array("f", stock[lo : lo + WIDTH]),
                array("f", mixed[lo : lo + WIDTH]),
            )
            if not metrics["bitwise"] and first[slot] is None:
                first[slot] = stage
            per_slot.append(metrics)
        stages[stage] = per_slot
    stock_weighted = read_f32(
        root / "layer2-stock-ffn_moe_weighted.f32", WIDTH * SLOTS)
    mixed_weighted = read_f32(
        root / "layer2-mixed-ffn_moe_weighted.f32", WIDTH * SLOTS)
    stock_ffn = read_f32(root / "layer2-stock-ffn.f32", WIDTH)
    mixed_ffn = read_f32(root / "layer2-mixed-ffn.f32", WIDTH)
    stock_order_stock = sum_slots(stock_weighted, (0, 1, 2, 3))
    stock_order_mixed = sum_slots(mixed_weighted, (0, 1, 2, 3))
    subset_order_mixed = mixed_subset_sum(mixed_weighted)
    return {
        "schema": "tesy.vertical_numerical_stage_analysis.v1",
        "classification": "DIAGNOSTIC_RECOMPUTATION_NOT_ACCEPTANCE",
        "route": list(ROUTE),
        "resident_gpu_ids": sorted(RESIDENT),
        "mapping": mapping,
        "first_non_bitwise_stage_by_slot": first,
        "stage_parity_by_slot": stages,
        "stock_association": "(((slot0+slot1)+slot2)+slot3)",
        "mixed_association": "sum(GPU slots in route order)+sum(CPU slots in route order)",
        "stock_weighted_stock_association_vs_stock_ffn": parity(
            stock_ffn, stock_order_stock),
        "mixed_weighted_mixed_association_vs_mixed_ffn": parity(
            mixed_ffn, subset_order_mixed),
        "mixed_weighted_stock_association_vs_stock_ffn": parity(
            stock_ffn, stock_order_mixed),
        "mixed_weighted_stock_vs_subset_association": parity(
            stock_order_mixed, subset_order_mixed),
        "mixed_ffn_vs_stock_ffn": parity(stock_ffn, mixed_ffn),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyse(args.root)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "first_non_bitwise_stage_by_slot": result["first_non_bitwise_stage_by_slot"],
        "stock_reconstruction_bitwise": result[
            "stock_weighted_stock_association_vs_stock_ffn"]["bitwise"],
        "mixed_reconstruction_bitwise": result[
            "mixed_weighted_mixed_association_vs_mixed_ffn"]["bitwise"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
