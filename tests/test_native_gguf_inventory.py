import json

import pytest

from tesy.native_gguf_inventory import (
    NativeGGUFInventoryError,
    derive_native_expert_inventory,
    parse_native_inventory_jsonl,
)


def _line(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"))


def _fixture() -> str:
    rows = [
        {
            "schema": "tesy.gguf_native_inventory_header.v1",
            "gguf_version": 3,
            "alignment": 32,
            "data_offset": 4096,
            "tensor_count": 3,
        },
        {
            "schema": "tesy.gguf_native_tensor.v1",
            "id": 0,
            "name": "blk.0.ffn_gate_exps.weight",
            "shape": [8, 16, 4],
            "tensor_type": "Q4_0",
            "n_bytes": 128,
            "relative_data_offset": 0,
            "data_offset": 4096,
        },
        {
            "schema": "tesy.gguf_native_tensor.v1",
            "id": 1,
            "name": "blk.0.ffn_up_exps.weight",
            "shape": [8, 16, 4],
            "tensor_type": "Q4_0",
            "n_bytes": 256,
            "relative_data_offset": 128,
            "data_offset": 4224,
        },
        {
            "schema": "tesy.gguf_native_tensor.v1",
            "id": 2,
            "name": "token_embd.weight",
            "shape": [8, 16],
            "tensor_type": "F16",
            "n_bytes": 256,
            "relative_data_offset": 384,
            "data_offset": 4480,
        },
    ]
    return "\n".join(_line(row) for row in rows) + "\n"


def test_parse_native_inventory_preserves_file_dimension_order():
    header, records = parse_native_inventory_jsonl(_fixture())
    assert header["tensor_count"] == 3
    assert records[0].shape == (8, 16, 4)
    assert records[0].data_offset == 4096


def test_native_inventory_derives_expert_bytes_without_external_python_deps():
    payload = derive_native_expert_inventory(_fixture())
    assert payload["status"] == "PASS_DERIVATION"
    assert payload["tensor_count_total"] == 3
    assert len(payload["layers"]) == 1
    layer = payload["layers"][0]
    assert layer["expert_count"] == 4
    assert layer["encoded_payload_bytes_per_expert"] == 96
    assert [tensor["shape"] for tensor in layer["tensors"]] == [
        [8, 16, 4],
        [8, 16, 4],
    ]
    assert "no gguf-py" in payload["claim_boundary"]


def test_native_inventory_rejects_absolute_offset_mismatch():
    rows = [json.loads(line) for line in _fixture().splitlines()]
    rows[1]["data_offset"] += 1
    text = "\n".join(_line(row) for row in rows) + "\n"

    with pytest.raises(NativeGGUFInventoryError, match="absolute data offset mismatch"):
        parse_native_inventory_jsonl(text)


def test_native_inventory_rejects_duplicate_tensor_name():
    rows = [json.loads(line) for line in _fixture().splitlines()]
    rows[2]["name"] = rows[1]["name"]
    text = "\n".join(_line(row) for row in rows) + "\n"

    with pytest.raises(NativeGGUFInventoryError, match="duplicate tensor name"):
        parse_native_inventory_jsonl(text)


def test_native_inventory_rejects_count_mismatch():
    rows = [json.loads(line) for line in _fixture().splitlines()]
    rows[0]["tensor_count"] = 4
    text = "\n".join(_line(row) for row in rows) + "\n"

    with pytest.raises(NativeGGUFInventoryError, match="tensor count mismatch"):
        parse_native_inventory_jsonl(text)
