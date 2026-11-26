from pathlib import Path
from runpy import run_path

import pytest

bench = run_path(str(Path(__file__).with_name("bench.py")))


def test_interaction_uses_paired_blocks():
    def block(times):
        return {cell: {"s": {"ns": t}} for cell, t in zip("ABCD", times, strict=True)}

    rows = [block([20, 15, 17, 11])] * 3 + [block([20, 13, 15, 16])]
    out = bench["contrast"](rows)
    assert out["passes"]
    assert out["blocks"][0]["interaction"] == 1
    assert out["effects"]["policy_on_pack"] == {"positive": 3, "median_ns": 4.0}


def test_short_read_preserves_failure(tmp_path):
    path = tmp_path / "short.bin"
    path.write_bytes(b"abc")
    with path.open("rb") as f, pytest.raises(ValueError, match="short aligned read"):
        bench["read_at"](f.fileno(), bytearray(4), 4, 0)
