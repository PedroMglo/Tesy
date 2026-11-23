from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


class RawTraceError(ValueError):
    pass


@dataclass(frozen=True)
class RawRouteEvent:
    step: int
    input_token_id: int
    layer: int
    experts: tuple[int, ...]


def _non_negative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RawTraceError(f"{field} must be a non-negative integer")
    return value


def parse_raw_event(payload: object) -> RawRouteEvent:
    if not isinstance(payload, dict):
        raise RawTraceError("raw trace event must be an object")
    required = {"step", "input_token_id", "layer", "phase", "experts"}
    if set(payload) != required:
        raise RawTraceError(f"raw trace keys must be exactly {sorted(required)}")
    if payload["phase"] != "decode":
        raise RawTraceError("raw tracer v1 only admits decode events")

    step = _non_negative_int(payload["step"], "step")
    input_token_id = _non_negative_int(payload["input_token_id"], "input_token_id")
    layer = _non_negative_int(payload["layer"], "layer")

    raw_experts = payload["experts"]
    if not isinstance(raw_experts, list) or not raw_experts:
        raise RawTraceError("experts must be a non-empty list")
    experts = tuple(_non_negative_int(item, "expert") for item in raw_experts)
    if len(set(experts)) != len(experts):
        raise RawTraceError("duplicate expert within a routed layer")

    return RawRouteEvent(
        step=step,
        input_token_id=input_token_id,
        layer=layer,
        experts=experts,
    )


def read_raw_jsonl(path: Path) -> list[RawRouteEvent]:
    events: list[RawRouteEvent] = []
    seen: set[tuple[int, int]] = set()
    previous: tuple[int, int] | None = None
    token_by_step: dict[int, int] = {}

    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RawTraceError(f"line {line_no}: invalid JSON: {exc}") from exc
            try:
                event = parse_raw_event(payload)
            except RawTraceError as exc:
                raise RawTraceError(f"line {line_no}: {exc}") from exc

            key = (event.step, event.layer)
            if key in seen:
                raise RawTraceError(f"line {line_no}: duplicate step/layer {key}")
            if previous is not None and key <= previous:
                raise RawTraceError(f"line {line_no}: out-of-order step/layer {key}")
            seen.add(key)
            previous = key

            old_token = token_by_step.setdefault(event.step, event.input_token_id)
            if old_token != event.input_token_id:
                raise RawTraceError(
                    f"line {line_no}: input token changed within step {event.step}"
                )
            events.append(event)

    if not events:
        raise RawTraceError("raw trace is empty")
    return events


def summarize_raw(
    events: list[RawRouteEvent],
    expected_layers: int | None = None,
    expected_top_k: int | None = None,
    expected_experts: int | None = None,
) -> dict[str, object]:
    failures: list[str] = []
    by_step: Counter[int] = Counter()
    topks: set[int] = set()

    for event in events:
        by_step[event.step] += 1
        topks.add(len(event.experts))
        if expected_top_k is not None and len(event.experts) != expected_top_k:
            failures.append(
                f"step {event.step} layer {event.layer}: "
                f"top-k {len(event.experts)} != {expected_top_k}"
            )
        if expected_experts is not None:
            bad = [item for item in event.experts if item >= expected_experts]
            if bad:
                failures.append(
                    f"step {event.step} layer {event.layer}: out-of-range experts {bad}"
                )

    if expected_layers is not None:
        for step, count in sorted(by_step.items()):
            if count != expected_layers:
                failures.append(
                    f"step {step}: routed layer count {count} != {expected_layers}"
                )

    steps = sorted(by_step)
    if steps and steps != list(range(steps[-1] + 1)):
        failures.append(f"decode steps are not contiguous from zero: {steps}")

    return {
        "schema": "tesy.raw_route_summary.v1",
        "classification": "MEASURED_ROUTER_IDS_WHEN_SOURCE_IS_REAL_MODEL",
        "status": "PASS" if not failures else "FAIL",
        "events": len(events),
        "steps": len(by_step),
        "events_per_step": dict(sorted(by_step.items())),
        "observed_top_k_values": sorted(topks),
        "failures": failures,
        "claim_boundary": (
            "Router-ID instrumentation only. No expert byte traffic, cache benefit, "
            "performance or conversational quality is established."
        ),
    }
