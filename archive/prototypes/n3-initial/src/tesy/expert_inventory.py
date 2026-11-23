from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class ExpertInventoryError(ValueError):
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
        raise ExpertInventoryError(
            "expected_layers and expected_experts must be positive"
        )

    by_layer: dict[int, dict[str, int]] = {}

    for record in records:
        match = _EXPERT_WEIGHT_RE.match(record.name)
        if match is None:
            continue

        layer = int(match.group("layer"))
        role = match.group("role")
        if layer >= expected_layers:
            raise ExpertInventoryError(
                f"expert tensor layer {layer} exceeds expected layer count "
                f"{expected_layers}"
            )
        if len(record.shape) < 3:
            raise ExpertInventoryError(
                f"{record.name}: expected fused >=3D expert tensor, "
                f"got shape {record.shape}"
            )
        if record.shape[2] != expected_experts:
            raise ExpertInventoryError(
                f"{record.name}: expert axis {record.shape[2]} != "
                f"{expected_experts}"
            )
        if record.n_bytes <= 0 or record.n_bytes % expected_experts != 0:
            raise ExpertInventoryError(
                f"{record.name}: encoded bytes {record.n_bytes} are not "
                "positive/divisible by expert count"
            )

        roles = by_layer.setdefault(layer, {})
        if role in roles:
            raise ExpertInventoryError(
                f"duplicate expert tensor role {role} in layer {layer}"
            )
        roles[role] = record.n_bytes // expected_experts

    expected = set(range(expected_layers))
    observed = set(by_layer)
    if observed != expected:
        raise ExpertInventoryError(
            "expert tensor layer mismatch: "
            f"missing={sorted(expected - observed)} "
            f"extra={sorted(observed - expected)}"
        )

    role_sets = {tuple(sorted(roles)) for roles in by_layer.values()}
    if len(role_sets) != 1:
        raise ExpertInventoryError(
            f"inconsistent expert tensor roles across layers: {role_sets}"
        )

    layer_rows: list[dict[str, Any]] = []
    for layer in range(expected_layers):
        roles = by_layer[layer]
        layer_rows.append(
            {
                "layer": layer,
                "per_expert_encoded_weight_bytes": sum(roles.values()),
                "roles": dict(sorted(roles.items())),
            }
        )

    one_expert_each_layer = sum(
        row["per_expert_encoded_weight_bytes"] for row in layer_rows
    )

    return {
        "schema": "tesy.expert_inventory.v1",
        "classification": "GGUF_ENCODED_LAYOUT_DERIVED",
        "model_id": model_id,
        "layers": expected_layers,
        "experts_per_layer": expected_experts,
        "layer_experts": layer_rows,
        "one_expert_per_layer_encoded_weight_bytes": one_expert_each_layer,
        "all_expert_encoded_weight_bytes": one_expert_each_layer * expected_experts,
        "runtime_copy_reference": {
            "backend": "pinned llama.cpp",
            "operation": "GGML_OP_MUL_MAT_ID",
            "expert_axis": 2,
            "runtime_expert_stride": "input->nb[2]",
            "max_extra_padding_bytes_per_group_per_tensor": 512,
        },
        "claim_boundary": (
            "Encoded GGUF expert-weight footprint only. It is not measured "
            "NVMe, page-cache, DRAM, PCIe or CUDA transfer traffic, and does "
            "not include runtime allocation/repacking or selective-copy padding."
        ),
    }


def load_expert_inventory(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExpertInventoryError(f"cannot read inventory {path}: {exc}") from exc

    if payload.get("schema") != "tesy.expert_inventory.v1":
        raise ExpertInventoryError("unsupported expert inventory schema")
    rows = payload.get("layer_experts")
    experts = payload.get("experts_per_layer")
    if not isinstance(rows, list) or not rows:
        raise ExpertInventoryError("layer_experts must be a non-empty list")
    if isinstance(experts, bool) or not isinstance(experts, int) or experts <= 0:
        raise ExpertInventoryError("experts_per_layer must be a positive integer")

    seen: set[int] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ExpertInventoryError("inventory layer row must be an object")
        layer = row.get("layer")
        size = row.get("per_expert_encoded_weight_bytes")
        if (
            isinstance(layer, bool)
            or not isinstance(layer, int)
            or layer < 0
            or layer in seen
        ):
            raise ExpertInventoryError(
                "inventory layer IDs must be unique non-negative integers"
            )
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ExpertInventoryError(
                "per_expert_encoded_weight_bytes must be positive"
            )
        seen.add(layer)
    return payload


def write_json_no_replace(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
