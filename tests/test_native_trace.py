from __future__ import annotations

import json

import pytest

from tesy.native_trace import (
    NativeTraceError,
    parse_native_record,
    read_native_jsonl,
    require_explicit_phase,
    summarize_native,
)


def _record(graph, layer, rows, phase="decode"):
    return {
        "schema": "tesy.llama_moe_topk.v2",
        "graph_seq": graph,
        "phase": phase,
        "layer": layer,
        "n_tokens": len(rows),
        "n_expert_used": len(rows[0]),
        "experts": rows,
    }


def test_parse_native_record():
    record = parse_native_record(_record(0, 3, [[1, 2, 8, 9]]))
    assert record.phase == "decode"
    assert record.n_tokens == 1


def test_parse_legacy_v1_marks_phase_unknown():
    payload = _record(0, 3, [[1, 2]])
    payload.pop("phase")
    payload["schema"] = "tesy.llama_moe_topk.v1"
    record = parse_native_record(payload)
    assert record.phase is None
    with pytest.raises(NativeTraceError):
        require_explicit_phase([record])


def test_reject_duplicate_experts_in_topk():
    with pytest.raises(NativeTraceError):
        parse_native_record(_record(0, 3, [[1, 1, 8, 9]]))


def test_summarize_native_graph_shapes(tmp_path):
    path = tmp_path / "raw.jsonl"
    payloads = [
        _record(0, 0, [[1, 2], [1, 3]], "prefill"),
        _record(0, 1, [[4, 5], [4, 6]], "prefill"),
        _record(1, 0, [[1, 2]]),
        _record(1, 1, [[4, 5]]),
    ]
    path.write_text(
        "\n".join(json.dumps(payload) for payload in payloads) + "\n",
        encoding="utf-8",
    )
    summary = summarize_native(read_native_jsonl(path))
    assert summary["graphs"] == 2
    assert summary["multi_token_graphs"] == 1
    assert summary["one_token_graphs"] == 1
    assert summary["phase_metadata_complete"] is True


def test_native_trace_requires_monotonic_graph_layer(tmp_path):
    path = tmp_path / "raw.jsonl"
    payloads = [_record(1, 0, [[1, 2]]), _record(0, 1, [[4, 5]])]
    path.write_text(
        "\n".join(json.dumps(payload) for payload in payloads) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(NativeTraceError):
        read_native_jsonl(path)
