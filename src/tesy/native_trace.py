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
    phase: str | None = None

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

    schema = payload.get("schema")
    common = {
        "schema",
        "graph_seq",
        "layer",
        "n_tokens",
        "n_expert_used",
        "experts",
    }
    if schema == "tesy.llama_moe_topk.v1":
        if set(payload) != common:
            raise NativeTraceError("v1 native trace record has missing/extra keys")
        phase: str | None = None
    elif schema == "tesy.llama_moe_topk.v2":
        if set(payload) != common | {"phase"}:
            raise NativeTraceError("v2 native trace record has missing/extra keys")
        raw_phase = payload["phase"]
        if raw_phase not in {"prefill", "decode"}:
            raise NativeTraceError("phase must be prefill or decode")
        phase = raw_phase
    else:
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
        phase=phase,
    )


def read_native_jsonl(path: Path) -> list[NativeTopKRecord]:
    records: list[NativeTopKRecord] = []
    previous: tuple[int, int] | None = None
    phase_modes: set[bool] = set()
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

            phase_modes.add(record.phase is not None)
            if len(phase_modes) > 1:
                raise NativeTraceError(
                    "native trace mixes phase-aware and legacy records"
                )

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


def require_explicit_phase(records: list[NativeTopKRecord]) -> None:
    if not records or any(record.phase is None for record in records):
        raise NativeTraceError(
            "native trace lacks explicit prefill/decode phase metadata; "
            "rerun with tesy.llama_moe_topk.v2 tracer"
        )


def summarize_native(records: list[NativeTopKRecord]) -> dict[str, Any]:
    graph_shapes: dict[int, int] = {}
    graph_phases: dict[int, str | None] = {}
    layer_experts: set[tuple[int, int]] = set()
    per_graph_working_sets: dict[int, set[tuple[int, int]]] = {}

    for record in records:
        old = graph_shapes.setdefault(record.graph_seq, record.n_tokens)
        if old != record.n_tokens:
            raise NativeTraceError(
                f"graph {record.graph_seq} has inconsistent token counts"
            )
        old_phase = graph_phases.setdefault(record.graph_seq, record.phase)
        if old_phase != record.phase:
            raise NativeTraceError(
                f"graph {record.graph_seq} has inconsistent phase metadata"
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
        "schema": "tesy.native_trace_summary.v2",
        "classification": "MEASURED_ROUTER_IDS_DIAGNOSTIC",
        "records": len(records),
        "graphs": len(graph_shapes),
        "one_token_graphs": one_token_graphs,
        "multi_token_graphs": len(graph_shapes) - one_token_graphs,
        "phase_metadata_complete": all(
            phase is not None for phase in graph_phases.values()
        ),
        "unique_layer_experts": len(layer_experts),
        "mean_unique_layer_experts_per_graph": mean(counts),
        "min_unique_layer_experts_per_graph": min(counts),
        "max_unique_layer_experts_per_graph": max(counts),
        "graph_token_counts": [
            {
                "graph_seq": graph,
                "n_tokens": graph_shapes[graph],
                "phase": graph_phases[graph],
            }
            for graph in sorted(graph_shapes)
        ],
        "claim_boundary": (
            "These are routed expert IDs observed through llama.cpp cb_eval. "
            "No expert-byte, physical-I/O, acceptance or performance claim follows."
        ),
    }


def validate_one_token_graph_consistency(
    records: list[NativeTopKRecord],
    min_graph_seq: int = 0,
) -> dict[str, Any]:
    if isinstance(min_graph_seq, bool) or not isinstance(min_graph_seq, int):
        raise NativeTraceError("min_graph_seq must be an integer")
    if min_graph_seq < 0:
        raise NativeTraceError("min_graph_seq must be non-negative")
    require_explicit_phase(records)

    grouped: dict[int, list[NativeTopKRecord]] = {}
    for record in records:
        if (
            record.phase != "decode"
            or record.graph_seq < min_graph_seq
            or record.n_tokens != 1
        ):
            continue
        grouped.setdefault(record.graph_seq, []).append(record)

    if not grouped:
        raise NativeTraceError(
            "no one-token decode graphs available for consistency check"
        )

    signatures: dict[int, tuple[tuple[int, int], ...]] = {}
    for graph, graph_records in sorted(grouped.items()):
        signatures[graph] = tuple(
            (record.layer, record.n_expert_used)
            for record in graph_records
        )

    reference_graph = min(signatures)
    reference = signatures[reference_graph]
    mismatches = [
        {
            "graph_seq": graph,
            "signature": [list(item) for item in signature],
        }
        for graph, signature in signatures.items()
        if signature != reference
    ]

    status = "PASS" if not mismatches else "FAIL"
    return {
        "schema": "tesy.native_trace_consistency.v2",
        "classification": "MEASURED_ROUTER_STRUCTURE_DIAGNOSTIC",
        "status": status,
        "min_graph_seq": min_graph_seq,
        "phase_aware": True,
        "one_token_graphs_checked": len(signatures),
        "reference_graph_seq": reference_graph,
        "reference_signature": [list(item) for item in reference],
        "mismatches": mismatches,
        "claim_boundary": (
            "Checks only that one-token decode evaluation groups expose the same "
            "ordered MoE layer/top-k signature. PASS does not prove absolute token "
            "positions, expert-byte traffic, output exactness, or performance."
        ),
    }
