from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class InventoryError(ValueError):
    pass


_EXPERT_WEIGHT_RE = re.compile(
    r"^blk\.(?P<layer>\d+)\.ffn_(?P<role>down|gate|up|gate_up)_(?:ch)?exps\.weight$"
)


@dataclass(frozen=True)
class TensorRecord:
    name: str
    shape: tuple[int, ...]
    n_bytes: int


def build_expert_inventory(
    records: Iterable[TensorRecord],
    *,
    model_id: str,
    expected_layers: int,
    expected_experts: int,
) -> dict[str, Any]:
    if expected_layers <= 0 or expected_experts <= 0:
        raise InventoryError("expected_layers and expected_experts must be positive")

    by_layer: dict[int, dict[str, int]] = {}

    for record in records:
        match = _EXPERT_WEIGHT_RE.match(record.name)
        if match is None:
            continue

        layer = int(match.group("layer"))
        role = match.group("role")
        if layer >= expected_layers:
            raise InventoryError(
                f"expert tensor layer {layer} exceeds expected layer count {expected_layers}"
            )
        if len(record.shape) < 3:
            raise InventoryError(
                f"{record.name}: expected a fused 3D expert tensor, got shape {record.shape}"
            )
        if record.shape[2] != expected_experts:
            raise InventoryError(
                f"{record.name}: expert axis {record.shape[2]} != {expected_experts}"
            )
        if record.n_bytes <= 0 or record.n_bytes % expected_experts != 0:
            raise InventoryError(
                f"{record.name}: tensor bytes {record.n_bytes} not divisible by experts"
            )

        roles = by_layer.setdefault(layer, {})
        if role in roles:
            raise InventoryError(f"duplicate expert tensor role {role} in layer {layer}")
        roles[role] = record.n_bytes // expected_experts

    expected_layer_set = set(range(expected_layers))
    observed_layer_set = set(by_layer)
    missing = sorted(expected_layer_set - observed_layer_set)
    extra = sorted(observed_layer_set - expected_layer_set)
    if missing or extra:
        raise InventoryError(f"expert tensor layer mismatch: missing={missing} extra={extra}")

    role_sets = {tuple(sorted(roles)) for roles in by_layer.values()}
    if len(role_sets) != 1:
        raise InventoryError(f"inconsistent expert tensor roles across layers: {role_sets}")

    layer_rows = []
    for layer in range(expected_layers):
        roles = by_layer[layer]
        per_expert = sum(roles.values())
        layer_rows.append(
            {
                "layer": layer,
                "per_expert_weight_bytes": per_expert,
                "roles": dict(sorted(roles.items())),
            }
        )

    one_expert_every_layer = sum(
        row["per_expert_weight_bytes"] for row in layer_rows
    )
    total_all_experts = one_expert_every_layer * expected_experts

    return {
        "schema": "tesy.expert_inventory.v1",
        "classification": "GGUF_ENCODED_LAYOUT_DERIVED",
        "model_id": model_id,
        "layers": expected_layers,
        "experts_per_layer": expected_experts,
        "layer_experts": layer_rows,
        "one_expert_per_layer_weight_bytes": one_expert_every_layer,
        "all_expert_weight_bytes": total_all_experts,
        "scheduler_copy_model": {
            "source": "pinned llama.cpp GGML_OP_MUL_MAT_ID host-weight selective copy",
            "expert_axis": 2,
            "max_extra_padding_bytes_per_copied_group_per_tensor": 512,
        },
        "claim_boundary": (
            "Encoded fused expert weight bytes only. This is not measured NVMe, "
            "DRAM or PCIe traffic. Backend selective-copy padding is not included "
            "in per_expert_weight_bytes."
        ),
    }


def load_inventory(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InventoryError(f"cannot read inventory {path}: {exc}") from exc
    if payload.get("schema") != "tesy.expert_inventory.v1":
        raise InventoryError("unsupported expert inventory schema")
    layers = payload.get("layer_experts")
    if not isinstance(layers, list) or not layers:
        raise InventoryError("inventory layer_experts must be a non-empty list")
    seen: set[int] = set()
    for row in layers:
        if not isinstance(row, dict):
            raise InventoryError("inventory layer row must be an object")
        layer = row.get("layer")
        size = row.get("per_expert_weight_bytes")
        if (
            isinstance(layer, bool)
            or not isinstance(layer, int)
            or layer < 0
            or layer in seen
        ):
            raise InventoryError("inventory layer IDs must be unique non-negative integers")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise InventoryError("per_expert_weight_bytes must be a positive integer")
        seen.add(layer)
    return payload


def write_json_no_replace(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
