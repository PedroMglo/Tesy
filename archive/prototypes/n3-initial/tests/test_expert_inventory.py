from __future__ import annotations

import json

import pytest

from tesy.expert_inventory import (
    ExpertInventoryError,
    TensorRecord,
    build_expert_inventory,
)
from tesy.native_bytes import normalize_native_decode, write_jsonl_no_replace
from tesy.native_trace import NativeTopKRecord


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


def _inventory():
    return build_expert_inventory(
        _records(),
        model_id="fixture",
        expected_layers=2,
        expected_experts=4,
    )


def test_inventory_derives_encoded_per_expert_bytes():
    result = _inventory()
    assert result["layer_experts"][0]["per_expert_encoded_weight_bytes"] == 450
    assert result["one_expert_per_layer_encoded_weight_bytes"] == 900
    assert result["all_expert_encoded_weight_bytes"] == 3600


def test_inventory_rejects_wrong_expert_axis():
    rows = _records()
    rows[0] = TensorRecord(rows[0].name, (16, 8, 5), 400)
    with pytest.raises(ExpertInventoryError):
        build_expert_inventory(
            rows,
            model_id="fixture",
            expected_layers=2,
            expected_experts=4,
        )


def test_native_normalization_uses_one_token_graphs():
    records = [
        NativeTopKRecord(0, 0, ((1, 2), (2, 3))),
        NativeTopKRecord(1, 0, ((1, 3),)),
        NativeTopKRecord(1, 1, ((0, 2),)),
    ]
    rows, stats = normalize_native_decode(records, _inventory(), min_graph_seq=1)
    assert len(rows) == 2
    assert rows[0]["token"] == 1
    assert rows[0]["experts"] == [
        {"id": 1, "bytes": 450},
        {"id": 3, "bytes": 450},
    ]
    assert stats["skipped_before_min_graph_seq"] == 1


def test_native_normalization_rejects_out_of_range_expert():
    records = [NativeTopKRecord(1, 0, ((4,),))]
    with pytest.raises(ExpertInventoryError):
        normalize_native_decode(records, _inventory(), min_graph_seq=1)


def test_jsonl_writer_is_no_replace(tmp_path):
    path = tmp_path / "trace.jsonl"
    rows = [
        {
            "token": 1,
            "layer": 0,
            "phase": "decode",
            "experts": [{"id": 1, "bytes": 450}],
        }
    ]
    write_jsonl_no_replace(path, rows)
    assert json.loads(path.read_text(encoding="utf-8").strip()) == rows[0]
    with pytest.raises(FileExistsError):
        write_jsonl_no_replace(path, rows)
