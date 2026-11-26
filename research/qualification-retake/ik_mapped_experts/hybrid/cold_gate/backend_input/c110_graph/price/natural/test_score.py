"""The slot and file must both be contiguous, and the buffer may only recycle after a drain."""

from pathlib import Path
from runpy import run_path

import pytest

S = run_path(str(Path(__file__).with_name("score.py")))


def test_byte_windows():
    assert S["runs"]([(0, 2), (1, 3), (2, 5), (4, 6)]) == [[0, 2, 2], [2, 5, 1], [4, 6, 1]]
    assert S["lifetime"]([("gate", 4095, 0, 2), ("up", 0, 0, 4096)], 8192) == (12288, 1, 8192)
    assert S["lifetime"]([("gate", 4095, 0, 2), ("up", 0, 0, 4096)], 12288) == (12288, 0, 8192)
    with pytest.raises(ValueError, match="one SET"):
        S["lifetime"]([("gate", 4095, 0, 2)], 4096)
