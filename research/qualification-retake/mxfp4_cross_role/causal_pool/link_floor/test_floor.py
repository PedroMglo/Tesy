import unittest
from fractions import Fraction as F
from pathlib import Path
from runpy import run_path

m = run_path(Path(__file__).with_name("screen.py"))


class PhysicalFloor(unittest.TestCase):
    def test_shared_link_and_full_overlap(self):
        rows = [(F(4), 16), (F(0), 24)]
        self.assertEqual(m["extra_time"](rows, 8 * 10**9), 3)
        self.assertEqual(m["extra_time"]([(F(0), 4 * 24)], 8 * 10**9), 12)
        self.assertEqual(m["available_volume"](rows, F(1)), 24)

    def test_rate_exact_and_no_prior_headroom(self):
        rows = [(F(1), 16), (F(0), 16)]
        self.assertEqual(m["required"](rows, F(2)), 10666666667)
        self.assertIsNone(m["required"](rows, F(0)))
        self.assertIsNone(m["available_volume"](rows, F(-1, 10)))


if __name__ == "__main__":
    unittest.main()
