from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable


class TraceError(ValueError):
    pass


@dataclass(frozen=True, order=True)
class ExpertKey:
    layer: int
    expert: int


@dataclass(frozen=True)
class ExpertUse:
    key: ExpertKey
    encoded_bytes: int


@dataclass(frozen=True)
class RouteEvent:
    token: int
    layer: int
    phase: str
    experts: tuple[ExpertUse, ...]


def _require_int(value: object, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise TraceError(f"{field} must be an integer >= {minimum}")
    return value


def parse_event(payload: object) -> RouteEvent:
    if not isinstance(payload, dict):
        raise TraceError("trace event must be an object")
    allowed = {"token", "layer", "phase", "experts"}
    extra = set(payload) - allowed
    if extra:
        raise TraceError(f"unknown trace keys: {sorted(extra)}")
    token = _require_int(payload.get("token"), "token")
    layer = _require_int(payload.get("layer"), "layer")
    phase = payload.get("phase", "decode")
    if phase not in {"prefill", "decode"}:
        raise TraceError("phase must be prefill or decode")
    raw_experts = payload.get("experts")
    if not isinstance(raw_experts, list) or not raw_experts:
        raise TraceError("experts must be a non-empty list")
    experts: list[ExpertUse] = []
    seen: set[int] = set()
    for index, raw in enumerate(raw_experts):
        if not isinstance(raw, dict) or set(raw) != {"id", "bytes"}:
            raise TraceError(f"experts[{index}] must contain exactly id and bytes")
        expert = _require_int(raw["id"], f"experts[{index}].id")
        encoded_bytes = _require_int(raw["bytes"], f"experts[{index}].bytes", minimum=1)
        if expert in seen:
            raise TraceError(f"duplicate expert {expert} in layer event")
        seen.add(expert)
        experts.append(
            ExpertUse(ExpertKey(layer=layer, expert=expert), encoded_bytes)
        )
    return RouteEvent(token=token, layer=layer, phase=phase, experts=tuple(experts))


def read_jsonl(path: Path) -> list[RouteEvent]:
    events: list[RouteEvent] = []
    previous: tuple[int, int] | None = None
    sizes: dict[ExpertKey, int] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TraceError(f"line {line_no}: invalid JSON: {exc}") from exc
            try:
                event = parse_event(payload)
            except TraceError as exc:
                raise TraceError(f"line {line_no}: {exc}") from exc
            position = (event.token, event.layer)
            if previous is not None and position <= previous:
                relation = "duplicate" if position == previous else "out-of-order"
                raise TraceError(
                    f"line {line_no}: {relation} token/layer event {position}"
                )
            previous = position
            for use in event.experts:
                old = sizes.setdefault(use.key, use.encoded_bytes)
                if old != use.encoded_bytes:
                    raise TraceError(
                        f"line {line_no}: inconsistent byte size for {use.key}"
                    )
            events.append(event)
    if not events:
        raise TraceError("trace is empty")
    return events


def token_working_sets(
    events: Iterable[RouteEvent],
    phase: str = "decode",
) -> list[tuple[int, dict[ExpertKey, int]]]:
    by_token: dict[int, dict[ExpertKey, int]] = {}
    for event in events:
        if event.phase != phase:
            continue
        target = by_token.setdefault(event.token, {})
        for use in event.experts:
            old = target.setdefault(use.key, use.encoded_bytes)
            if old != use.encoded_bytes:
                raise TraceError(f"inconsistent expert size for {use.key}")
    return [(token, by_token[token]) for token in sorted(by_token)]


def summarize(events: list[RouteEvent]) -> dict[str, object]:
    sizes: dict[ExpertKey, int] = {}
    uses = 0
    phases: dict[str, int] = {"prefill": 0, "decode": 0}
    layers: set[int] = set()
    tokens: set[int] = set()
    for event in events:
        phases[event.phase] += 1
        layers.add(event.layer)
        tokens.add(event.token)
        for use in event.experts:
            uses += 1
            sizes[use.key] = use.encoded_bytes
    return {
        "schema": "tesy.trace_summary.v1",
        "events": len(events),
        "expert_uses": uses,
        "tokens": len(tokens),
        "layers": len(layers),
        "unique_layer_experts": len(sizes),
        "unique_expert_bytes": sum(sizes.values()),
        "events_by_phase": phases,
    }


def window_union_metrics(
    events: list[RouteEvent],
    window: int,
    phase: str = "decode",
) -> dict[str, object]:
    if isinstance(window, bool) or not isinstance(window, int) or window <= 0:
        raise TraceError("window must be a positive integer")
    tokens = token_working_sets(events, phase=phase)
    if not tokens:
        raise TraceError(f"trace has no {phase} tokens")

    windows: list[tuple[int, int]] = []
    for start in range(0, len(tokens), window):
        chunk = tokens[start : start + window]
        union: dict[ExpertKey, int] = {}
        for _, experts in chunk:
            for key, size in experts.items():
                old = union.setdefault(key, size)
                if old != size:
                    raise TraceError(f"inconsistent expert size for {key}")
        windows.append((len(chunk), sum(union.values())))

    union_bytes = [item[1] for item in windows]
    bytes_per_token = [byte_count / token_count for token_count, byte_count in windows]
    return {
        "schema": "tesy.speculative_union.v1",
        "classification": "TRACE_DERIVED_UPPER_BOUND_NOT_ACCEPTANCE",
        "phase": phase,
        "window": window,
        "window_count": len(windows),
        "token_count": sum(item[0] for item in windows),
        "mean_distinct_expert_bytes_per_window": mean(union_bytes),
        "mean_distinct_expert_bytes_per_token_if_loaded_once_per_window": mean(
            bytes_per_token
        ),
        "min_distinct_expert_bytes_per_window": min(union_bytes),
        "max_distinct_expert_bytes_per_window": max(union_bytes),
        "claim_boundary": (
            "This measures routed expert union in observed target tokens. "
            "It does not measure speculative acceptance or predict future routing."
        ),
    }
