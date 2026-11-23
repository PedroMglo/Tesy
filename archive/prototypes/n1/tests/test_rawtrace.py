from __future__ import annotations

import json

import pytest

from tesy.rawtrace import RawTraceError, parse_raw_event, read_raw_jsonl, summarize_raw


def _payload(step: int, layer: int, token: int = 11, experts=(1, 3)):
    return {
        "step": step,
        "input_token_id": token,
        "layer": layer,
        "phase": "decode",
        "experts": list(experts),
    }


def test_raw_summary_passes_expected_geometry():
    events = [
        parse_raw_event(_payload(0, 0)),
        parse_raw_event(_payload(0, 1)),
        parse_raw_event(_payload(1, 0, token=12)),
        parse_raw_event(_payload(1, 1, token=12)),
    ]
    result = summarize_raw(
        events,
        expected_layers=2,
        expected_top_k=2,
        expected_experts=4,
    )
    assert result["status"] == "PASS"


def test_raw_summary_rejects_out_of_range_expert():
    result = summarize_raw(
        [parse_raw_event(_payload(0, 0, experts=(1, 9)))],
        expected_layers=1,
        expected_top_k=2,
        expected_experts=4,
    )
    assert result["status"] == "FAIL"


def test_raw_trace_rejects_changed_input_token_within_step(tmp_path):
    path = tmp_path / "trace.jsonl"
    lines = [
        _payload(0, 0, token=11),
        _payload(0, 1, token=12),
    ]
    path.write_text("\n".join(json.dumps(item) for item in lines) + "\n", encoding="utf-8")
    with pytest.raises(RawTraceError):
        read_raw_jsonl(path)


def test_raw_trace_rejects_extra_keys():
    payload = _payload(0, 0)
    payload["future"] = [4]
    with pytest.raises(RawTraceError):
        parse_raw_event(payload)
