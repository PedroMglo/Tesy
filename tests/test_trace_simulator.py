from __future__ import annotations

import json

import pytest

from tesy.simulator import simulate_demand_lru
from tesy.trace import TraceError, parse_event, read_jsonl, window_union_metrics


def _event(token: int, layer: int, experts: list[tuple[int, int]]):
    return parse_event(
        {
            "token": token,
            "layer": layer,
            "phase": "decode",
            "experts": [{"id": expert, "bytes": size} for expert, size in experts],
        }
    )


def test_window_union_reuses_same_layer_expert():
    events = [
        _event(0, 0, [(1, 100), (2, 100)]),
        _event(1, 0, [(1, 100), (3, 100)]),
    ]
    k1 = window_union_metrics(events, 1)
    k2 = window_union_metrics(events, 2)
    assert k1["mean_distinct_expert_bytes_per_token_if_loaded_once_per_window"] == 200
    assert k2["mean_distinct_expert_bytes_per_window"] == 300
    assert k2["mean_distinct_expert_bytes_per_token_if_loaded_once_per_window"] == 150


def test_demand_lru_counts_nvme_and_pcie_separately():
    events = [
        _event(0, 0, [(1, 100)]),
        _event(1, 0, [(1, 100)]),
    ]
    result = simulate_demand_lru(events, ram_cache_bytes=100, vram_cache_bytes=100)
    assert result["nvme_to_ram_expert_bytes"] == 100
    assert result["ram_to_vram_expert_bytes"] == 100
    assert result["vram_cache"]["hits"] == 1


def test_no_vram_capacity_requires_transfer_on_each_use():
    events = [
        _event(0, 0, [(1, 100)]),
        _event(1, 0, [(1, 100)]),
    ]
    result = simulate_demand_lru(events, ram_cache_bytes=100, vram_cache_bytes=0)
    assert result["nvme_to_ram_expert_bytes"] == 100
    assert result["ram_to_vram_expert_bytes"] == 200


def test_reject_duplicate_expert():
    with pytest.raises(TraceError):
        parse_event(
            {
                "token": 0,
                "layer": 0,
                "phase": "decode",
                "experts": [{"id": 1, "bytes": 100}, {"id": 1, "bytes": 100}],
            }
        )


def test_trace_payload_rejects_extra_keys():
    payload = {
        "token": 0,
        "layer": 0,
        "phase": "decode",
        "experts": [{"id": 1, "bytes": 100}],
        "future_router": [2],
    }
    with pytest.raises(TraceError):
        parse_event(json.loads(json.dumps(payload)))


def test_trace_file_rejects_duplicate_token_layer(tmp_path):
    path = tmp_path / "trace.jsonl"
    line = json.dumps(
        {
            "token": 0,
            "layer": 0,
            "phase": "decode",
            "experts": [{"id": 1, "bytes": 100}],
        }
    )
    path.write_text(f"{line}\n{line}\n", encoding="utf-8")
    with pytest.raises(TraceError):
        read_jsonl(path)
