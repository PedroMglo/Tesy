from __future__ import annotations

import pytest

from tesy.native_trace import NativeTopKRecord, NativeTraceError
from tesy.weighted_trace import WeightedTraceError, native_decode_to_weighted_events


def _inventory():
    return {
        "schema": "tesy.gguf_expert_inventory.v1",
        "status": "PASS_DERIVATION",
        "classification": "GGUF_ENCODED_PAYLOAD_DERIVED",
        "layers": [
            {"layer": 0, "expert_count": 4, "encoded_payload_bytes_per_expert": 100},
            {"layer": 1, "expert_count": 4, "encoded_payload_bytes_per_expert": 200},
        ],
    }


def _record(graph, layer, experts, phase="decode"):
    return NativeTopKRecord(
        graph_seq=graph,
        layer=layer,
        experts=experts,
        phase=phase,
    )


def test_native_decode_becomes_weighted_events():
    events = native_decode_to_weighted_events(
        [_record(1, 0, ((1, 2),)), _record(1, 1, ((0, 3),))],
        _inventory(),
    )
    assert len(events) == 2
    assert [use.encoded_bytes for use in events[0].experts] == [100, 100]


def test_one_token_prefill_is_not_decode():
    events = native_decode_to_weighted_events(
        [
            _record(0, 0, ((0,),), "prefill"),
            _record(1, 0, ((2,),), "decode"),
        ],
        _inventory(),
    )
    assert len(events) == 1
    assert events[0].token == 1


def test_trace_expert_must_fit_inventory():
    with pytest.raises(WeightedTraceError):
        native_decode_to_weighted_events(
            [_record(1, 0, ((4,),))],
            _inventory(),
        )


def test_inventory_must_have_passed_derivation():
    inventory = _inventory()
    inventory["status"] = "INCONCLUSIVE"
    with pytest.raises(WeightedTraceError):
        native_decode_to_weighted_events(
            [_record(1, 0, ((1,),))],
            inventory,
        )


def test_legacy_trace_without_phase_is_rejected():
    with pytest.raises(NativeTraceError):
        native_decode_to_weighted_events(
            [_record(0, 0, ((1,),), None)],
            _inventory(),
        )
