from __future__ import annotations

import json

import pytest

from tesy.native_trace import (
    NativeTraceError,
    parse_native_record,
    read_native_jsonl,
    summarize_native,
)


def _record(graph: int, layer: int, rows: list[list[int]]) -> dict[str, object]:
    return {
        "schema": "tesy.llama_moe_topk.v1",
        "graph_seq": graph,
        "layer": layer,
        "n_tokens": len(rows),
        "n_expert_used": len(rows[0]),
        "experts": rows,
    }


def test_parse_native_record() -> None:
    record = parse_native_record(_record(0, 3, [[1, 2, 8, 9]]))
    assert record.graph_seq == 0
    assert record.layer == 3
    assert record.n_tokens == 1
    assert record.n_expert_used == 4


def test_reject_duplicate_experts_in_topk() -> None:
    with pytest.raises(NativeTraceError):
        parse_native_record(_record(0, 3, [[1, 1, 8, 9]]))


def test_summarize_native_graph_shapes(tmp_path) -> None:
    path = tmp_path / "raw.jsonl"
    payloads = [
        _record(0, 0, [[1, 2], [1, 3]]),
        _record(0, 1, [[4, 5], [4, 6]]),
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
    assert summary["unique_layer_experts"] == 6


def test_native_trace_requires_monotonic_graph_layer(tmp_path) -> None:
    path = tmp_path / "raw.jsonl"
    payloads = [
        _record(1, 0, [[1, 2]]),
        _record(0, 1, [[4, 5]]),
    ]
    path.write_text(
        "\n".join(json.dumps(payload) for payload in payloads) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(NativeTraceError):
        read_native_jsonl(path)
