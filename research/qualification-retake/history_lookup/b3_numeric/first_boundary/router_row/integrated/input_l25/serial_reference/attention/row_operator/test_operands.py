import struct
from pathlib import Path
from runpy import run_path

import pytest

grade = run_path(str(Path(__file__).with_name("operands.py")))["grade"]


def test_baselines_padding_and_mutation_gate_repair():
    serial, block, zero = [struct.pack("<f", x) * 12288 for x in (1, 2, 0)]
    refs = {"AR": serial, "B3": block}
    outputs = {
        "A": serial,
        "B": block,
        "B-alt": block,
        "S": serial,
        "S-alt": serial,
        "mutant": zero,
    }
    assert grade(outputs, refs)["decision"] == "GO_EXACT_ROW_ATTENTION_OPERATOR"
    assert grade(outputs | {"A": block}, refs)["decision"] == "INCONCLUSIVE_NATIVE_BASELINES"
    assert grade(outputs | {"mutant": block}, refs)["decision"] == "INCONCLUSIVE_FAULT_OR_PADDING"
    assert grade(outputs | {"B-alt": serial}, refs)["decision"] == "INCONCLUSIVE_FAULT_OR_PADDING"
    assert (
        grade(outputs | {"S": block, "S-alt": block}, refs)["decision"]
        == "NO_GO_ROW_ATTENTION_OPERATOR"
    )
    with pytest.raises(ValueError, match="nonfinite"):
        grade(outputs | {"S": b"\x00\x00\xc0\x7f" + serial[4:]}, refs)
