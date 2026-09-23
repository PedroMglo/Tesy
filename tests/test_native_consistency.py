from __future__ import annotations

from tesy.native_trace import NativeTopKRecord, validate_one_token_graph_consistency


def _record(graph, layer, width=2, phase="decode"):
    return NativeTopKRecord(
        graph_seq=graph,
        layer=layer,
        experts=(tuple(range(width)),),
        phase=phase,
    )


def test_consistency_passes_equal_decode_signatures():
    records = [
        _record(0, 0, phase="prefill"),
        _record(0, 1, phase="prefill"),
        _record(1, 0),
        _record(1, 1),
        _record(2, 0),
        _record(2, 1),
    ]
    result = validate_one_token_graph_consistency(records)
    assert result["status"] == "PASS"
    assert result["one_token_graphs_checked"] == 2


def test_consistency_fails_missing_layer():
    result = validate_one_token_graph_consistency(
        [_record(0, 0), _record(0, 1), _record(1, 0)]
    )
    assert result["status"] == "FAIL"


def test_consistency_fails_changed_topk_width():
    result = validate_one_token_graph_consistency(
        [_record(0, 0, 2), _record(1, 0, 3)]
    )
    assert result["status"] == "FAIL"
