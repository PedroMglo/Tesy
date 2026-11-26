import unittest
from fractions import Fraction
from pathlib import Path
from runpy import run_path

mod = run_path(Path(__file__).with_name("screen.py"))
W = mod["W"]


class PriceTests(unittest.TestCase):
    def test_set_after_read_is_preserved_in_maximum(self):
        callbacks = [[(1, 20, 2), (2, 16, 9)], [(3, None, 0), (4, 6, 0)]]
        total, local, n = mod["service"](callbacks, lambda k: W // 2)
        self.assertEqual(total - mod["cost"]["OUTSIDE"] * W, 20 * W)
        self.assertEqual((local, n), ([3 * W], 1))

    def test_uniform_unknown_price_respects_both_clocks_and_rounding(self):
        decode = 3_000_000_000 * W
        limit = mod["cost"]["BUDGET"] * W
        # Half a nanosecond beyond the wall allowance must not buy an extra ns.
        pf = Fraction(limit - decode - 7 * W) + W // 2
        row = mod["crossed"](pf, decode, [3 * W], 0)
        self.assertEqual(row["joint_margin_ns_floor"], 6)
        self.assertEqual(row["new_read_uniform_effective_ns_max"], 9)
        self.assertIsNone(
            mod["crossed"](pf, decode, [3 * W], 7)["new_read_uniform_effective_ns_max"]
        )


if __name__ == "__main__":
    unittest.main()
