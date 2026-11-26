import hashlib
import json
import struct
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

import pytest

R = run_path(str(Path(__file__).with_name("run.py")))
OPS, A = R["OPS"], R["AUTH"]


@pytest.mark.parametrize(
    "marks,now,label",
    [
        ({}, 180.5, "load"),
        ({"L": 170}, 260.01, "context"),
        ({"L": 100, "C": 175}, 265.01, "prefill"),
        ({"L": 100, "C": 175, "P": 245}, 335.01, "teacher"),
        ({"L": 100, "C": 175, "P": 245, "T": 290}, 300.01, "cleanup"),
        ({"L": 175, "C": 260, "P": 345, "T": 430, "F": 435}, 461, "total"),
    ],
)
def test_deadline(marks, now, label):
    with pytest.raises(ValueError, match=label):
        OPS["check_time"](0, marks, now)


def test_ready_and_failed_rows_survive(tmp_path):
    native = tmp_path / "native"
    native.mkdir()
    unique = bytearray(804352)
    struct.pack_into("<f", unique, 3659 * 4, 1.0)
    (native / "pos15.f32").write_bytes(unique)
    row = OPS["written_row"](native, 15)
    got = {}
    OPS["row_gate"](got, 15, row)
    assert got["15"]["sha256"] == hashlib.sha256(unique).hexdigest()
    struct.pack_into("<f", unique, 5 * 4, 1.0)
    (native / "pos15.f32").write_bytes(unique)
    row = OPS["written_row"](native, 15)
    with pytest.raises(ValueError, match="greedy"):
        OPS["row_gate"](got, 15, row)
    assert got["15"]["max_ties"] == 2 and R["available_rows"](tmp_path)["15"] == row
    (native / "pos16.f32").write_bytes(b"partial")
    assert R["available_rows"](tmp_path)["16"]["bytes"] == 7
    with pytest.raises(ValueError, match="partial"):
        OPS["written_row"](native, 16)


def test_gpu_and_model_present_after_initial_allocation():
    OPS["owner"]("E", [], 613)
    OPS["owner"]("F", [], 613)
    for tag in ("L", "C", "P", "T"):
        OPS["owner"](tag, [613], 613)
        with pytest.raises(ValueError, match="absent"):
            OPS["owner"](tag, [], 613)
        with pytest.raises(ValueError):
            OPS["owner"](tag, [613, 614], 613)


def test_no_second_arm_if_first_stops(tmp_path):
    seen = []

    def fail(_a, folder, mode, *_):
        seen.append(mode)
        return {"status": "FAIL_PRESERVED"}

    with pytest.raises(ValueError, match="BANK288 gate"):
        R["sequence"](None, tmp_path, {}, None, None, fail)
    assert seen == ["BANK288"] and not (tmp_path / "BANK161").exists()


def test_c55_rejects_other_unit_before_read():
    with pytest.raises(ValueError, match="dedicated"):
        A["c55"](SimpleNamespace(c55=Path("/tmp/tesy-ik-capacity-c55-20261126-r01/receipt.json")))


def test_capacity_failure_even_with_valid_digest(tmp_path):
    rec = tmp_path / "receipt.json"
    rec.write_text(json.dumps({"status": "FAIL_PRESERVED"}))
    with pytest.raises(ValueError, match="physical capacity"):
        A["capacity_gate"](
            SimpleNamespace(
                capacity=tmp_path, capacity_sha256=hashlib.sha256(rec.read_bytes()).hexdigest()
            )
        )


def test_negative_logits_cannot_admit_bank161():
    fake = {
        "grade": {
            "status": "PASS_IK_GPU_BANK_ARM",
            "slots": 288,
            "group_layers": 36,
            "consumer_ops": 432,
            "sites": 72,
            "ordered_quartets": 597,
            "logits_sha256": {"pos15.f32": "a", "pos16.f32": "b"},
        },
        "model_starts": 1,
        "returncode": 0,
        "swap_peak": 0,
        "restored": True,
        "child_gone": True,
        "ack_elapsed_s": dict.fromkeys(OPS["PHASE"], 0),
        "rows_at_ack": {
            "15": {"sha256": "a", "finite": True, "max_ties": 1, "top5": [3659]},
            "16": {"sha256": "b", "finite": True, "max_ties": 1, "top5": [3992]},
        },
    }
    R["ready"]("BANK288", fake)
    fake["rows_at_ack"]["16"]["top5"] = [0]
    with pytest.raises(ValueError, match="unqualified"):
        R["ready"]("BANK288", fake)


def test_ids_different_input_rejected(tmp_path):
    inp = tmp_path / "ids"
    inp.write_bytes(b"\0" * 68)
    with pytest.raises(ValueError, match="IDs or teacher"):
        A["input_ids"](inp)


@pytest.mark.parametrize("teacher,passes", [(976, True), (977, False)])
def test_teacher_gate_with_known_prefix(tmp_path, monkeypatch, teacher, passes):
    path = tmp_path / "ids.i32"
    prefix = struct.pack("<16i", *range(16))
    raw = prefix + struct.pack("<i", teacher)
    path.write_bytes(raw)
    gate = A["input_ids"]
    monkeypatch.setitem(gate.__globals__, "PREFIX", hashlib.sha256(prefix).hexdigest())
    monkeypatch.setitem(gate.__globals__, "IDS", hashlib.sha256(raw).hexdigest())
    if passes:
        assert gate(path) == hashlib.sha256(raw).hexdigest()
    else:
        with pytest.raises(ValueError, match="teacher"):
            gate(path)
