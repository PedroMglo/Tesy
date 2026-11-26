"""Reject a matrix span disguised as an expert bias without opening any real weights."""

import unittest
from pathlib import Path
from runpy import run_path

U = run_path(str(Path(__file__).with_name("prepare_warm.py")))


class ExtentTests(unittest.TestCase):
    def test_only_absolute_bias_range(self):
        model = U["P"]
        c = dict(
            name="blk.1.ffn_down_exps.bias",
            size_bytes=11520,
            type="f32",
            packed_relative_offset=model["WINDOW"] + 11520,
            sha256="11" * 32,
        )
        rec = dict(
            layer=1, expert=20, pack_offset=148 * model["STRIDE"], components=[None] * 4 + [c, None]
        )
        start, n, _ = U["bias_range"](rec, 1)
        self.assertEqual((start, n), (148 * model["STRIDE"] + model["WINDOW"] + 11520, 11520))
        c["packed_relative_offset"] = model["SLAB"]
        with self.assertRaisesRegex(ValueError, "bias-only"):
            U["bias_range"](rec, 1)


if __name__ == "__main__":
    unittest.main()
