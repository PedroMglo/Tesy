from tesy.mixed_residency import mixed_residency_hit_histogram
from tesy.native_trace import NativeTopKRecord


def _inventory() -> dict:
    return {
        "schema": "tesy.gguf_expert_inventory.v1",
        "status": "PASS_DERIVATION",
        "layers": [
            {
                "layer": 0,
                "expert_count": 8,
                "encoded_payload_bytes_per_expert": 10,
            }
        ],
    }


def test_mixed_residency_histogram_tracks_top4_hits_before_insertions():
    records = [
        NativeTopKRecord(graph_seq=1, layer=0, experts=((0, 1, 2, 3),)),
        NativeTopKRecord(graph_seq=2, layer=0, experts=((0, 1, 4, 5),)),
        NativeTopKRecord(graph_seq=3, layer=0, experts=((0, 1, 2, 3),)),
    ]

    payload = mixed_residency_hit_histogram(
        records,
        _inventory(),
        vram_capacity_bytes=80,
        min_graph_seq=1,
    )

    assert payload["expert_uses"] == 12
    assert payload["hits"] == 6
    assert payload["misses"] == 6
    assert payload["hit_rate"] == 0.5
    assert payload["gpu_resident_experts_per_top4_histogram"] == {
        "0": 1,
        "1": 0,
        "2": 2,
        "3": 0,
        "4": 0,
    }


def test_mixed_residency_histogram_respects_byte_capacity_eviction():
    records = [
        NativeTopKRecord(graph_seq=1, layer=0, experts=((0, 1, 2, 3),)),
        NativeTopKRecord(graph_seq=2, layer=0, experts=((0, 1, 2, 3),)),
    ]

    payload = mixed_residency_hit_histogram(
        records,
        _inventory(),
        vram_capacity_bytes=20,
        min_graph_seq=1,
    )

    assert payload["hit_rate"] == 0.0
    assert payload["gpu_resident_experts_per_top4_histogram"]["0"] == 2
    assert payload["evictions"] == 6


def test_mixed_residency_histogram_filters_graph_prefix():
    records = [
        NativeTopKRecord(graph_seq=0, layer=0, experts=((0, 1, 2, 3),)),
        NativeTopKRecord(graph_seq=1, layer=0, experts=((0, 1, 2, 3),)),
    ]

    payload = mixed_residency_hit_histogram(
        records,
        _inventory(),
        vram_capacity_bytes=80,
        min_graph_seq=1,
    )

    assert payload["routing_groups"] == 1
    assert payload["committed_tokens_proxy"] == 1
    assert payload["hits"] == 0
