from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tesy.expert_inventory import ExpertInventoryError
from tesy.native_trace import NativeTopKRecord


def _sizes(inventory: dict[str, Any]) -> tuple[dict[int, int], int]:
    if inventory.get("schema") != "tesy.expert_inventory.v1":
        raise ExpertInventoryError("unsupported expert inventory schema")

    expert_count = inventory.get("experts_per_layer")
    if (
        isinstance(expert_count, bool)
        or not isinstance(expert_count, int)
        or expert_count <= 0
    ):
        raise ExpertInventoryError("invalid experts_per_layer")

    sizes: dict[int, int] = {}
    for row in inventory.get("layer_experts", []):
        if not isinstance(row, dict):
            raise ExpertInventoryError("invalid inventory layer row")
        layer = row.get("layer")
        size = row.get("per_expert_encoded_weight_bytes")
        if (
            isinstance(layer, bool)
            or not isinstance(layer, int)
            or layer < 0
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
            or layer in sizes
        ):
            raise ExpertInventoryError("invalid/duplicate inventory layer entry")
        sizes[layer] = size

    if not sizes:
        raise ExpertInventoryError("inventory contains no layer sizes")
    return sizes, expert_count


def normalize_native_decode(
    records: list[NativeTopKRecord],
    inventory: dict[str, Any],
    *,
    min_graph_seq: int = 1,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if isinstance(min_graph_seq, bool) or min_graph_seq < 0:
        raise ValueError("min_graph_seq must be a non-negative integer")

    sizes, expert_count = _sizes(inventory)
    rows: list[dict[str, Any]] = []
    skipped_multi = 0
    skipped_early = 0

    for record in records:
        if record.graph_seq < min_graph_seq:
            skipped_early += 1
            continue
        if record.n_tokens != 1:
            skipped_multi += 1
            continue
        if record.layer not in sizes:
            raise ExpertInventoryError(
                f"trace layer {record.layer} is absent from expert inventory"
            )

        experts = record.experts[0]
        bad = [expert for expert in experts if expert >= expert_count]
        if bad:
            raise ExpertInventoryError(
                f"trace layer {record.layer} has out-of-range experts {bad}"
            )

        rows.append(
            {
                "token": record.graph_seq,
                "layer": record.layer,
                "phase": "decode",
                "experts": [
                    {
                        "id": expert,
                        "bytes": sizes[record.layer],
                    }
                    for expert in experts
                ],
            }
        )

    if not rows:
        raise ExpertInventoryError(
            "no one-token graph records remain after normalization filters"
        )

    return rows, {
        "normalized_records": len(rows),
        "skipped_before_min_graph_seq": skipped_early,
        "skipped_multi_token_records": skipped_multi,
    }


def write_jsonl_no_replace(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True))
            handle.write("\n")
