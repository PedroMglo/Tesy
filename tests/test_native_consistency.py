from __future__ import annotations

from tesy.native_trace import NativeTopKRecord, validate_one_token_graph_consistency


def _record(graph: int, layer: int, width: int = 2) -> NativeTopKRecord:
    experts = tuple(range(width))
    return NativeTopKRecord(graph_seq=graph, layer=layer, experts=(experts,))


def test_consistency_passes_equal_graph_signatures():
    records = [
        _record(0, 0),
        _record(0, 1),
        _record(1, 0),
        _record(1, 1),
    ]
    result = validate_one_token_graph_consistency(records)
    assert result["status"] == "PASS"
    assert result["one_token_graphs_checked"] == 2


def test_consistency_fails_missing_layer():
    records = [
        _record(0, 0),
        _record(0, 1),
        _record(1, 0),
    ]
    result = validate_one_token_graph_consistency(records)
    assert result["status"] == "FAIL"
    assert result["mismatches"]


def test_consistency_fails_changed_topk_width():
    records = [
        _record(0, 0, width=2),
        _record(1, 0, width=3),
    ]
    result = validate_one_token_graph_consistency(records)
    assert result["status"] == "FAIL"
