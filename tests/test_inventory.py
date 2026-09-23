from __future__ import annotations

import pytest

from tesy.inventory import InventoryError, TensorRecord, build_expert_inventory
from tesy.normalize import normalize_raw_events
from tesy.rawtrace import RawRouteEvent


def _records():
    rows = []
    for layer in range(2):
        rows.extend(
            [
                TensorRecord(
                    f"blk.{layer}.ffn_gate_exps.weight", (16, 8, 4), 400
                ),
                TensorRecord(
                    f"blk.{layer}.ffn_up_exps.weight", (16, 8, 4), 800
                ),
                TensorRecord(
                    f"blk.{layer}.ffn_down_exps.weight", (8, 16, 4), 600
                ),
            ]
        )
    return rows


def test_inventory_derives_per_expert_bytes():
    result = build_expert_inventory(
        _records(),
        model_id="fixture",
        expected_layers=2,
        expected_experts=4,
    )
    assert result["layer_experts"][0]["per_expert_weight_bytes"] == 450
    assert result["one_expert_per_layer_weight_bytes"] == 900
    assert result["all_expert_weight_bytes"] == 3600


def test_inventory_rejects_wrong_expert_axis():
    rows = _records()
    rows[0] = TensorRecord(rows[0].name, (16, 8, 5), 400)
    with pytest.raises(InventoryError):
        build_expert_inventory(
            rows,
            model_id="fixture",
            expected_layers=2,
            expected_experts=4,
        )


def test_normalize_raw_attaches_layer_expert_bytes():
    inventory = build_expert_inventory(
        _records(),
        model_id="fixture",
        expected_layers=2,
        expected_experts=4,
    )
    events = [
        RawRouteEvent(step=0, input_token_id=10, layer=0, experts=(1, 3)),
        RawRouteEvent(step=0, input_token_id=10, layer=1, experts=(0, 2)),
    ]
    normalized = normalize_raw_events(events, inventory)
    assert normalized[0]["experts"] == [
        {"id": 1, "bytes": 450},
        {"id": 3, "bytes": 450},
    ]


def test_normalize_rejects_out_of_range_expert():
    inventory = build_expert_inventory(
        _records(),
        model_id="fixture",
        expected_layers=2,
        expected_experts=4,
    )
    with pytest.raises(InventoryError):
        normalize_raw_events(
            [RawRouteEvent(step=0, input_token_id=10, layer=0, experts=(4,))],
            inventory,
        )
