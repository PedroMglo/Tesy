"""Controls for authenticated partial output and a tie behind an unchanged greedy ID."""

import json
import struct
from pathlib import Path
from runpy import run_path

import pytest

R = run_path(str(Path(__file__).with_name("review.py")))


def test_describe_requires_unique_finite_maximum_for_gating():
    tied = R["describe"](struct.pack("<3f", 1.0, 1.0, -1.0), 3)
    assert tied["top5"] == [0, 1, 2] and tied["max_ties"] == 2
    invalid = R["describe"](struct.pack("<2f", 1.0, float("nan")), 2)
    assert invalid["finite"] is False and invalid["nonfinite"] == 1 and not invalid["top5"]


def test_failed_arm_preserves_one_row_but_pass_cannot_omit_second(tmp_path):
    raw = tmp_path / "capture"
    raw.mkdir()
    row = bytes(R["WIDTH"])
    (raw / "pos15.f32").write_bytes(row)
    facts = {"arm": "D0", "status": "FAIL_GREEDY", "logits_sha256": {"pos15.f32": R["digest"](row)}}
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps(facts))
    rows, _ = R["candidate"]("D0", tmp_path, R["digest"](receipt.read_bytes()))
    assert rows == {15: row}
    facts["status"] = "PASS_IK_CPU_NUMERIC_ARM"
    receipt.write_text(json.dumps(facts))
    with pytest.raises(ValueError, match="missing a cut"):
        R["candidate"]("D0", tmp_path, R["digest"](receipt.read_bytes()))
