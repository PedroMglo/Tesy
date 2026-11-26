import itertools
import unittest
from pathlib import Path
from runpy import run_path

M = run_path(str(Path(__file__).with_name("dual.py")))


class DualTest(unittest.TestCase):
    def test_exact_roundtrip_and_faults(self):
        fs = [((0,), 16), ((0, 1), 19), ((1, 2), 21), ((2,), 8)]
        zero = M["verify"](fs, [0, 0, 0, 0], 1)
        self.assertEqual(zero, 64)
        for cap in (1, 2):
            expected = max(
                sum(w for keys, w in fs if set(kept) & set(keys))
                for kept in itertools.combinations(range(3), cap)
            )
            suggested = M["propose"](fs, cap)
            for shares in (suggested, [16, 1, 20, 7], [0, 0, 0, 0]):
                self.assertGreaterEqual(M["verify"](fs, shares, cap), expected)
        for bad in ([16, 20, 21, 0], [16, -1, 0, 0], [1, 2, 3], [True, 2, 3, 4]):
            with self.assertRaises(ValueError):
                M["verify"](fs, bad, 1)

    def test_chord_dominates_enumeration_across_rounding(self):
        samples = [(4, [3, 11, 27]), (2, [0, 16, 15])]

        def possible(scale):
            return max(m - sum((h * scale) // 1_000_000 for h in row) for m, row in samples)

        clocks = {
            "P106.first": {
                "possible_callbacks": 3,
                "upper_ns": {str(s): possible(s) for s in M["S"]["SCALES"]},
            }
        }
        first = M["frontier"](clocks)["first_certified_no_go_ppm"]
        self.assertGreater(first, 0)
        for s in range(first, 1_000_001, 101):
            self.assertLess(possible(s), 0)


if __name__ == "__main__":
    unittest.main()
