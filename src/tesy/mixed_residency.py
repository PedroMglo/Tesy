from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

from tesy.native_trace import NativeTopKRecord, NativeTraceError, read_native_jsonl


class MixedResidencyError(ValueError):
    pass


def _inventory_sizes(inventory: dict[str, Any]) -> dict[int, tuple[int, int]]:
    if inventory.get("schema") != "tesy.gguf_expert_inventory.v1":
        raise MixedResidencyError("unsupported inventory schema")
    if inventory.get("status") != "PASS_DERIVATION":
        raise MixedResidencyError("inventory is not PASS_DERIVATION")

    layers = inventory.get("layers")
    if not isinstance(layers, list) or not layers:
        raise MixedResidencyError("inventory has no layers")

    result: dict[int, tuple[int, int]] = {}
    for row in layers:
        if not isinstance(row, dict):
            raise MixedResidencyError("inventory layer must be an object")
        layer = row.get("layer")
        count = row.get("expert_count")
        size = row.get("encoded_payload_bytes_per_expert")
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (layer, count, size)
        ):
            raise MixedResidencyError("inventory layer/count/size must be integers")
        if layer < 0 or count <= 0 or size <= 0:
            raise MixedResidencyError("inventory layer/count/size out of range")
        if layer in result:
            raise MixedResidencyError(f"duplicate inventory layer {layer}")
        result[layer] = (count, size)
    return result


def mixed_residency_hit_histogram(
    records: list[NativeTopKRecord],
    inventory: dict[str, Any],
    *,
    vram_capacity_bytes: int,
    min_graph_seq: int = 0,
) -> dict[str, Any]:
    if (
        isinstance(vram_capacity_bytes, bool)
        or not isinstance(vram_capacity_bytes, int)
        or vram_capacity_bytes < 0
    ):
        raise MixedResidencyError("vram_capacity_bytes must be a non-negative integer")
    if (
        isinstance(min_graph_seq, bool)
        or not isinstance(min_graph_seq, int)
        or min_graph_seq < 0
    ):
        raise MixedResidencyError("min_graph_seq must be a non-negative integer")

    sizes = _inventory_sizes(inventory)
    cache: OrderedDict[tuple[int, int], int] = OrderedDict()
    used_bytes = 0
    groups = 0
    expert_uses = 0
    hits = 0
    misses = 0
    evictions = 0
    histogram: dict[int, int] = {}
    graph_ids: set[int] = set()

    for record in records:
        if record.graph_seq < min_graph_seq or record.n_tokens != 1:
            continue
        graph_ids.add(record.graph_seq)
        if record.layer not in sizes:
            raise MixedResidencyError(
                f"trace layer {record.layer} missing from inventory"
            )
        expert_count, expert_bytes = sizes[record.layer]
        row = record.experts[0]
        if len(row) != 4:
            raise MixedResidencyError(
                f"expected top-4 routed experts, got {len(row)} at "
                f"graph={record.graph_seq} layer={record.layer}"
            )

        resident_hits = 0
        for expert in row:
            if expert >= expert_count:
                raise MixedResidencyError(
                    f"expert {expert} outside expert_count {expert_count}"
                )
            key = (record.layer, expert)
            expert_uses += 1
            if key in cache:
                cache.move_to_end(key)
                resident_hits += 1
                hits += 1
                continue

            misses += 1
            if expert_bytes > vram_capacity_bytes:
                continue
            while used_bytes + expert_bytes > vram_capacity_bytes and cache:
                _, evicted_bytes = cache.popitem(last=False)
                used_bytes -= evicted_bytes
                evictions += 1
            cache[key] = expert_bytes
            used_bytes += expert_bytes

        histogram[resident_hits] = histogram.get(resident_hits, 0) + 1
        groups += 1

    if groups == 0:
        raise NativeTraceError(
            "no one-token top-4 routing groups remain after filtering"
        )

    if sum(histogram.values()) != groups:
        raise RuntimeError("internal mixed-residency histogram corruption")
    if hits + misses != expert_uses:
        raise RuntimeError("internal mixed-residency hit accounting corruption")

    return {
        "schema": "tesy.mixed_residency_hit_histogram.v1",
        "classification": "TRACE_DERIVED_RESIDENCY_OPPORTUNITY",
        "policy": "DEMAND_TRIGGERED_LRU_IDEAL_TIMELY_INSERTION",
        "min_graph_seq": min_graph_seq,
        "vram_capacity_bytes": vram_capacity_bytes,
        "routing_groups": groups,
        "committed_tokens_proxy": len(graph_ids),
        "expert_uses": expert_uses,
        "hits": hits,
        "misses": misses,
        "hit_rate": hits / expert_uses,
        "evictions": evictions,
        "final_used_bytes": used_bytes,
        "gpu_resident_experts_per_top4_histogram": {
            str(hit_count): histogram.get(hit_count, 0)
            for hit_count in range(5)
        },
        "gpu_resident_experts_per_top4_fraction": {
            str(hit_count): histogram.get(hit_count, 0) / groups
            for hit_count in range(5)
        },
        "claim_boundary": (
            "Trace-derived opportunity only. A miss is inserted into the hypothetical "
            "LRU immediately for future accesses, which assumes any residency transfer "
            "completes in time and does not block the current demand. The histogram is "
            "not measured runtime residency, prefetch accuracy or mixed-execution latency."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--vram-cache-gib", required=True, type=float)
    parser.add_argument("--min-graph-seq", type=int, default=0)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to replace {args.output}")
    if args.vram_cache_gib < 0:
        raise SystemExit("vram-cache-gib must be non-negative")

    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    payload = mixed_residency_hit_histogram(
        read_native_jsonl(args.trace),
        inventory,
        vram_capacity_bytes=int(args.vram_cache_gib * 1024**3),
        min_graph_seq=args.min_graph_seq,
    )

    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
