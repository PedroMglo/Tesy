import copy
import json
import struct
from pathlib import Path

import pytest

from tesy.live_moe_reinjection_continuation_exactness import (
    ReinjectionValidationError,
    validate,
)


def _parity():
    return {
        "max_abs": 0.0,
        "max_abs_ref": 1.0,
        "relative_max": 0.0,
        "cosine": 1.0,
        "status": "PASS",
    }


def _fixture(tmp_path: Path) -> Path:
    count = 100001
    data = struct.pack(f"<{count}f", *([1.0] * count))
    arms = {}
    for name, hits in (("stock", 0), ("control", 0), ("h2", 2), ("h3", 3)):
        for checkpoint in ("a", "b"):
            (tmp_path / f"{name}-{checkpoint}.f32").write_bytes(data)
        arms[name] = {
            "gpu_hits": hits,
            "first_token": 2167,
            "second_token": 1309,
            "third_token": 100,
            "committed_decode_return_code": 0,
            "continuation_decode_return_code": 0,
            "stock_capture_rollback": True,
            "handoff_capture_rollback": True,
            "activation_pair_bitwise": True,
            "ffn_bitwise": True,
            "pre_overwrite_bitwise": True,
            "injected_bytes_verified": True,
            "injection_count": 0 if name == "stock" else 1,
            "selected_experts": [] if name == "stock" else [1, 13, 17, 21],
            "routing_weights": [] if name == "stock" else [0.4, 0.3, 0.2, 0.1],
            "activation_pair_parity": _parity(),
            "ffn_parity": _parity(),
            "pre_overwrite_parity": _parity(),
            "logits_a_file": f"{name}-a.f32",
            "logits_b_file": f"{name}-b.f32",
        }
    raw = {
        "schema": "tesy.live_moe_reinjection_continuation_exactness_raw.v1",
        "layer": 0,
        "ngl": 0,
        "first_token": 2167,
        "second_token": 1309,
        "stock_third_token": 100,
        "logits_count": count,
        "arms": arms,
        "claim_boundary": "correctness only",
    }
    path = tmp_path / "raw.json"
    path.write_text(json.dumps(raw))
    return path


def test_valid_four_arm_continuation(tmp_path):
    summary = validate(_fixture(tmp_path))
    assert summary["decision"] == "LIVE_MOE_REINJECTION_CONTINUATION_EXACTNESS_GO"
    assert summary["arms"]["h2"]["checkpoint_b"]["bitwise_equal"] is True


@pytest.mark.parametrize(
    "mutation",
    [
        lambda raw: raw.update({"median_ms": 1.0}),
        lambda raw: raw["arms"]["h2"].update({"injection_count": 2}),
        lambda raw: raw["arms"]["control"].update({"ffn_bitwise": False}),
        lambda raw: raw["arms"]["h3"].update({"third_token": 101}),
        lambda raw: raw["arms"]["h2"].update({"selected_experts": [1, 13, 17, 22]}),
        lambda raw: raw["arms"]["h2"].update({"stock_capture_rollback": False}),
        lambda raw: raw["arms"]["h2"].update({"logits_b_file": "../stock-b.f32"}),
    ],
)
def test_fail_closed_metadata_mutations(tmp_path, mutation):
    path = _fixture(tmp_path)
    raw = copy.deepcopy(json.loads(path.read_text()))
    mutation(raw)
    path.write_text(json.dumps(raw))
    with pytest.raises(ReinjectionValidationError):
        validate(path)


def test_fail_closed_logits_mutation(tmp_path):
    path = _fixture(tmp_path)
    name = tmp_path / "h2-b.f32"
    data = bytearray(name.read_bytes())
    data[:4] = struct.pack("<f", 2.0)
    name.write_bytes(data)
    with pytest.raises(ReinjectionValidationError):
        validate(path)
