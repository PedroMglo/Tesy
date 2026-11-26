import struct
from pathlib import Path
from runpy import run_path

import pytest

pair = run_path(str(Path(__file__).with_name("pair.py")))


def test_preprojection_projection_and_visibility(tmp_path):
    ar, block = (tmp_path / label for label in ("ar", "block"))
    for root in (ar, block):
        (root / "boundary").mkdir(parents=True)
        for pos in (189, 190, 191):
            for name, width in ((pair["NAME"], 4096), ("attn_out-25", 2880)):
                changed = root == block and (pos == 189 or (pos == 190 and width == 2880))
                words = [float(changed)] + [0.0] * (width - 1)
                (root / "boundary" / f"{pos}.{name}.bin").write_bytes(
                    struct.pack(f"<{width}f", *words)
                )
            cells = [0, 0xFC00]
            if root == block:
                cells = [0, 0, 0, 0xFC00]
            (root / f"mask-25-{pos}.f16").write_bytes(struct.pack(f"<{len(cells)}H", *cells))
    rows = pair["grade_pair"](ar, block)["positions"]
    assert [r["diagnosis"] for r in rows.values()] == [
        "DIFFERENT_BEFORE_OUTPUT_PROJECTION",
        "DIFFERENT_AT_OUTPUT_PROJECTION_OR_BIAS",
        "SAME_AT_BOTH_CUTS",
    ]
    assert rows["189"]["mask"]["trailing_unmatched_visible"] == 1
    assert rows["189"]["mask"]["first_different_cell"] == 1
    assert rows["189"]["mask"]["common_cells_different"] == 1
    assert pair["grade_pair"](ar, ar)["positions"]["189"]["mask"]["trailing_unmatched_visible"] == 0


def test_noncanonical_mask_fails(tmp_path):
    file = tmp_path / "mask"
    file.write_bytes(struct.pack("<HH", 0, 0x8000))
    with pytest.raises((ValueError, RuntimeError, AssertionError), match="mask bits"):
        pair["mask"](file)
