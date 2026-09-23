from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any


class NativeTraceError(ValueError):
    pass


@dataclass(frozen=True)
class NativeTopKRecord:
    graph_seq: int
    layer: int
    experts: tuple[tuple[int, ...], ...]

    @property
    def n_tokens(self) -> int:
        return len(self.experts)

    @property
    def n_expert_used(self) -> int:
        return len(self.experts[0]) if self.experts else 0


def _integer(value: object, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise NativeTraceError(f"{name} must be an integer >= {minimum}")
    return value


def parse_native_record(payload: object) -> NativeTopKRecord:
    if not isinstance(payload, dict):
        raise NativeTraceError("native trace record must be an object")
    allowed = {
        "schema",
        "graph_seq",
        "layer",
        "n_tokens",
        "n_expert_used",
        "experts",
    }
    if set(payload) != allowed:
        raise NativeTraceError("native trace record has missing/extra keys")
    if payload["schema"] != "tesy.llama_moe_topk.v1":
        raise NativeTraceError("unsupported native trace schema")

    graph_seq = _integer(payload["graph_seq"], "graph_seq")
    layer = _integer(payload["layer"], "layer")
    n_tokens = _integer(payload["n_tokens"], "n_tokens", minimum=1)
    n_expert_used = _integer(
        payload["n_expert_used"], "n_expert_used", minimum=1
    )
    raw_experts = payload["experts"]
    if not isinstance(raw_experts, list) or len(raw_experts) != n_tokens:
        raise NativeTraceError("experts must contain exactly n_tokens rows")

    rows: list[tuple[int, ...]] = []
    for token_index, row in enumerate(raw_experts):
        if not isinstance(row, list) or len(row) != n_expert_used:
            raise NativeTraceError(
                f"experts[{token_index}] must contain n_expert_used values"
            )
        parsed = tuple(
            _integer(value, f"experts[{token_index}][]") for value in row
        )
        if len(set(parsed)) != len(parsed):
            raise NativeTraceError(
                f"experts[{token_index}] contains duplicate expert IDs"
            )
        rows.append(parsed)

    return NativeTopKRecord(
        graph_seq=graph_seq,
        layer=layer,
        experts=tuple(rows),
    )


def read_native_jsonl(path: Path) -> list[NativeTopKRecord]:
    records: list[NativeTopKRecord] = []
    previous: tuple[int, int] | None = None
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise NativeTraceError(
                    f"line {line_no}: invalid JSON: {exc}"
                ) from exc
            try:
                record = parse_native_record(payload)
            except NativeTraceError as exc:
                raise NativeTraceError(f"line {line_no}: {exc}") from exc
            position = (record.graph_seq, record.layer)
            if previous is not None and position <= previous:
                raise NativeTraceError(
                    f"line {line_no}: non-monotonic graph/layer order"
                )
            previous = position
            records.append(record)
    if not records:
        raise NativeTraceError("native trace is empty")
    return records


def summarize_native(records: list[NativeTopKRecord]) -> dict[str, Any]:
    graph_shapes: dict[int, int] = {}
    layer_experts: set[tuple[int, int]] = set()
    per_graph_working_sets: dict[int, set[tuple[int, int]]] = {}

    for record in records:
        old = graph_shapes.setdefault(record.graph_seq, record.n_tokens)
        if old != record.n_tokens:
            raise NativeTraceError(
                f"graph {record.graph_seq} has inconsistent token counts"
            )
        working_set = per_graph_working_sets.setdefault(record.graph_seq, set())
        for row in record.experts:
            for expert in row:
                key = (record.layer, expert)
                layer_experts.add(key)
                working_set.add(key)

    counts = [len(items) for _, items in sorted(per_graph_working_sets.items())]
    one_token_graphs = sum(1 for size in graph_shapes.values() if size == 1)

    return {
        "schema": "tesy.native_trace_summary.v1",
        "classification": "MEASURED_ROUTER_IDS_DIAGNOSTIC",
        "records": len(records),
        "graphs": len(graph_shapes),
        "one_token_graphs": one_token_graphs,
        "multi_token_graphs": len(graph_shapes) - one_token_graphs,
        "unique_layer_experts": len(layer_experts),
        "mean_unique_layer_experts_per_graph": mean(counts),
        "min_unique_layer_experts_per_graph": min(counts),
        "max_unique_layer_experts_per_graph": max(counts),
        "graph_token_counts": [
            {"graph_seq": graph, "n_tokens": size}
            for graph, size in sorted(graph_shapes.items())
        ],
        "claim_boundary": (
            "These are routed expert IDs observed through llama.cpp cb_eval. "
            "No expert-byte, physical-I/O, acceptance or performance claim follows."
        ),
    }
