"""Faults in routing attribution and reference controls must survive a matching output."""

import struct
from pathlib import Path
from runpy import run_path

import pytest

D = run_path(str(Path(__file__).with_name("operands.py")))


def controls():
    wide = D["WIDTH"]
    a = bytes(3 * wide * 4)
    b = bytearray(a)
    for row, count in enumerate((33, 29, 109)):
        for i in range(count):
            struct.pack_into("<f", b, (wide * row + i) * 4, 0.5)
    block = bytes(b)
    struct.pack_into("<f", b, 0, 1.5)
    outputs = {t: a if t in ("A", "U", "S", "F", "F-alt") else block for t in D["TAGS"]}
    outputs["mutant"] = bytes(b)
    return outputs, {"AR": a, "B3": block}, [1, 2, 3, 4, 5, 6, 7, 8, 3, 4, 9, 10]


def test_preserve_both_controls_and_mutation_scope():
    out, refs, ids = controls()
    assert D["grade"](out, refs, ids)["matched_serial"] == ["U", "S", "F"]
    assert (
        D["grade"](dict(out, A=refs["B3"]), refs, ids)["decision"]
        == "INCONCLUSIVE_NATIVE_FFN_BASELINES"
    )
    assert (
        D["grade"](dict(out, mutant=refs["B3"]), refs, ids)["decision"]
        == "INCONCLUSIVE_FFN_CONTROLS"
    )
    wrong = bytearray(out["mutant"])
    struct.pack_into("<f", wrong, D["WIDTH"] * 4, 4.0)
    assert (
        D["grade"](dict(out, mutant=bytes(wrong)), refs, ids)["decision"]
        == "INCONCLUSIVE_FFN_CONTROLS"
    )


def test_nan_and_signed_zero():
    out, refs, ids = controls()
    bad = struct.pack("<f", float("nan")) + out["F"][4:]
    with pytest.raises((ValueError, RuntimeError)):
        D["grade"](dict(out, F=bad), refs, ids)
    negative_zero = struct.pack("<I", 1 << 31) + refs["AR"][4:]
    row = D["comparisons"](negative_zero, refs["AR"])[0]
    assert (row["different"], row["first"], row["max_abs"]) == (1, 0, 0.0)
