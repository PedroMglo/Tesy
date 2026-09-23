from __future__ import annotations

import pytest

from tesy.native_trace import NativeTopKRecord
from tesy.weighted_trace import WeightedTraceError, native_decode_to_weighted_events


def _inventory() -> dict:
    return {
        "schema": "tesy.gguf_expert_inventory.v1",
        "status": "PASS_DERIVATION",
        "classification": "GGUF_ENCODED_PAYLOAD_DERIVED",
        "layers": [
            {
                "layer": 0,
                "expert_count": 4,
                "encoded_payload_bytes_per_expert": 100,
            },
            {
                "layer": 1,
                "expert_count": 4,
                "encoded_payload_bytes_per_expert": 200,
            },
        ],
    }


def test_native_decode_becomes_weighted_events():
    records = [
        NativeTopKRecord(graph_seq=0, layer=0, experts=((1, 2),)),
        NativeTopKRecord(graph_seq=0, layer=1, experts=((0, 3),)),
    ]
    events = native_decode_to_weighted_events(records, _inventory())
    assert len(events) == 2
    assert events[0].token == 0
    assert [use.encoded_bytes for use in events[0].experts] == [100, 100]
    assert [use.encoded_bytes for use in events[1].experts] == [200, 200]


def test_multi_token_prefill_record_is_skipped():
    records = [
        NativeTopKRecord(graph_seq=0, layer=0, experts=((0,), (1,))),
        NativeTopKRecord(graph_seq=1, layer=0, experts=((2,),)),
    ]
    events = native_decode_to_weighted_events(records, _inventory())
    assert len(events) == 1
    assert events[0].token == 1


def test_trace_expert_must_fit_inventory():
    records = [NativeTopKRecord(graph_seq=0, layer=0, experts=((4,),))]
    with pytest.raises(WeightedTraceError):
        native_decode_to_weighted_events(records, _inventory())


def test_inventory_must_have_passed_derivation():
    inventory = _inventory()
    inventory["status"] = "INCONCLUSIVE"
    records = [NativeTopKRecord(graph_seq=0, layer=0, experts=((1,),))]
    with pytest.raises(WeightedTraceError):
        native_decode_to_weighted_events(records, inventory)
