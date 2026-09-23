from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tesy.inventory import InventoryError
from tesy.rawtrace import RawRouteEvent


def _layer_sizes(inventory: dict[str, Any]) -> dict[int, int]:
    if inventory.get("schema") != "tesy.expert_inventory.v1":
        raise InventoryError("unsupported expert inventory schema")
    result: dict[int, int] = {}
    for row in inventory.get("layer_experts", []):
        if not isinstance(row, dict):
            raise InventoryError("invalid layer row")
        layer = row.get("layer")
        size = row.get("per_expert_weight_bytes")
        if (
            isinstance(layer, bool)
            or not isinstance(layer, int)
            or layer < 0
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size <= 0
        ):
            raise InventoryError("invalid layer inventory entry")
        if layer in result:
            raise InventoryError(f"duplicate layer in inventory: {layer}")
        result[layer] = size
    if not result:
        raise InventoryError("inventory has no layer sizes")
    return result


def normalize_raw_events(
    events: list[RawRouteEvent],
    inventory: dict[str, Any],
) -> list[dict[str, Any]]:
    sizes = _layer_sizes(inventory)
    expected_experts = inventory.get("experts_per_layer")
    if (
        isinstance(expected_experts, bool)
        or not isinstance(expected_experts, int)
        or expected_experts <= 0
    ):
        raise InventoryError("inventory experts_per_layer must be positive")

    normalized: list[dict[str, Any]] = []
    for event in events:
        if event.layer not in sizes:
            raise InventoryError(f"raw trace layer {event.layer} absent from inventory")
        bad = [expert for expert in event.experts if expert >= expected_experts]
        if bad:
            raise InventoryError(
                f"raw trace layer {event.layer} has out-of-range experts {bad}"
            )
        normalized.append(
            {
                "token": event.step,
                "layer": event.layer,
                "phase": "decode",
                "experts": [
                    {"id": expert, "bytes": sizes[event.layer]}
                    for expert in event.experts
                ],
            }
        )
    return normalized


def write_jsonl_no_replace(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True))
            handle.write("\n")
