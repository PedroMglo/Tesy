from __future__ import annotations

from typing import Any

from tesy.native_trace import NativeTopKRecord, NativeTraceError
from tesy.trace import ExpertKey, ExpertUse, RouteEvent


class WeightedTraceError(ValueError):
    pass


def _layer_sizes(inventory: dict[str, Any]) -> dict[int, tuple[int, int]]:
    if inventory.get("schema") != "tesy.gguf_expert_inventory.v1":
        raise WeightedTraceError("unsupported inventory schema")
    if inventory.get("status") != "PASS_DERIVATION":
        raise WeightedTraceError("expert inventory is not PASS_DERIVATION")
    layers = inventory.get("layers")
    if not isinstance(layers, list) or not layers:
        raise WeightedTraceError("inventory has no layers")

    result: dict[int, tuple[int, int]] = {}
    for row in layers:
        if not isinstance(row, dict):
            raise WeightedTraceError("inventory layer must be an object")
        layer = row.get("layer")
        count = row.get("expert_count")
        size = row.get("encoded_payload_bytes_per_expert")
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (layer, count, size)
        ):
            raise WeightedTraceError("inventory layer/count/size must be integers")
        if layer < 0 or count <= 0 or size <= 0:
            raise WeightedTraceError("inventory layer/count/size out of range")
        if layer in result:
            raise WeightedTraceError(f"duplicate inventory layer {layer}")
        result[layer] = (count, size)
    return result


def native_decode_to_weighted_events(
    records: list[NativeTopKRecord],
    inventory: dict[str, Any],
    min_graph_seq: int = 0,
) -> list[RouteEvent]:
    if isinstance(min_graph_seq, bool) or not isinstance(min_graph_seq, int):
        raise WeightedTraceError("min_graph_seq must be an integer")
    if min_graph_seq < 0:
        raise WeightedTraceError("min_graph_seq must be non-negative")

    sizes = _layer_sizes(inventory)
    events: list[RouteEvent] = []
    for record in records:
        if record.graph_seq < min_graph_seq or record.n_tokens != 1:
            continue
        if record.layer not in sizes:
            raise WeightedTraceError(
                f"trace layer {record.layer} missing from expert inventory"
            )
        expert_count, bytes_per_expert = sizes[record.layer]
        uses: list[ExpertUse] = []
        for expert in record.experts[0]:
            if expert >= expert_count:
                raise WeightedTraceError(
                    f"trace expert {expert} outside layer {record.layer} "
                    f"expert_count {expert_count}"
                )
            uses.append(
                ExpertUse(
                    key=ExpertKey(layer=record.layer, expert=expert),
                    encoded_bytes=bytes_per_expert,
                )
            )
        events.append(
            RouteEvent(
                token=record.graph_seq,
                layer=record.layer,
                phase="decode",
                experts=tuple(uses),
            )
        )

    if not events:
        raise NativeTraceError(
            "no one-token graph records remain for byte-weighted decode simulation"
        )
    return events
