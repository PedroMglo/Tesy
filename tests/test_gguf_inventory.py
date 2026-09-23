from __future__ import annotations

from tesy.gguf_inventory import TensorRecord, derive_expert_payload_inventory


def _tensor(name: str, shape: tuple[int, ...], n_bytes: int) -> TensorRecord:
    return TensorRecord(
        name=name,
        shape=shape,
        n_bytes=n_bytes,
        tensor_type="Q4_0",
        data_offset=4096,
    )


def test_derives_equal_encoded_payload_per_expert():
    result = derive_expert_payload_inventory(
        [
            _tensor("blk.0.ffn_gate_exps.weight", (8, 16, 4), 128),
            _tensor("blk.0.ffn_up_exps.weight", (8, 16, 4), 256),
            _tensor("blk.0.ffn_down_exps.weight", (16, 8, 4), 128),
            _tensor("blk.0.attn_q.weight", (8, 8), 64),
        ]
    )
    assert result["status"] == "PASS_DERIVATION"
    assert len(result["layers"]) == 1
    layer = result["layers"][0]
    assert layer["expert_count"] == 4
    assert layer["encoded_expert_tensor_bytes_total"] == 512
    assert layer["encoded_payload_bytes_per_expert"] == 128


def test_mismatched_expert_dimension_is_inconclusive():
    result = derive_expert_payload_inventory(
        [
            _tensor("blk.0.ffn_gate_exps.weight", (8, 16, 4), 128),
            _tensor("blk.0.ffn_up_exps.weight", (8, 16, 8), 256),
        ]
    )
    assert result["status"] == "INCONCLUSIVE"
    assert result["layers"] == []
    assert result["rejected"]


def test_nondivisible_payload_is_inconclusive():
    result = derive_expert_payload_inventory(
        [_tensor("blk.0.ffn_gate_exps.weight", (8, 16, 3), 128)]
    )
    assert result["status"] == "INCONCLUSIVE"
    assert result["rejected"]


def test_no_expert_tensors_is_inconclusive():
    result = derive_expert_payload_inventory(
        [_tensor("blk.0.attn_q.weight", (8, 8), 64)]
    )
    assert result["status"] == "INCONCLUSIVE"
    assert "no merged" in result["reason"]
