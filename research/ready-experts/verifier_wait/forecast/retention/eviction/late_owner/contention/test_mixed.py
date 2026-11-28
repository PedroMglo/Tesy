"""Test the time before a hit and after the hit has stopped."""

import unittest
from pathlib import Path
from runpy import run_path

M = run_path(Path(__file__).with_name("mixed.py"))


def read(i, a, b, layer=1):
    return [[layer, 0, 1, i], [2, 1, layer], 0, 0, 0, a, b]


class SplitTests(unittest.TestCase):
    def test_lead_cannot_be_removed_and_suffix_includes_a_gap(self):
        jobs = [read(0, 0, 20), read(1, 4, 6), read(2, 12, 15)]
        c, p = M["split"](jobs, {2, 3})
        self.assertEqual(
            [c[key][1] for key in ("equal_share", "simultaneous", "suffix", "whole")],
            [2, 5, 16, 20],
        )
        self.assertEqual(p["shapes"]["2/1"]["wall_ns"], 5)

    def test_mixed_site_and_two_hits_count_one_interval(self):
        c, p = M["split"]([read(0, 0, 9), read(1, 0, 9), read(2, 0, 9, 3)], {1, 3})
        self.assertEqual(c["equal_share"], {2: 6})
        self.assertEqual(c["simultaneous"], {2: 9})
        self.assertEqual(p["shapes"]["3/2"]["cross_site_wall_ns"], 9)

    def test_touch_has_no_credit(self):
        c, _ = M["split"]([read(0, 0, 3), read(1, 3, 6)], {2})
        self.assertFalse(any(c.values()))


if __name__ == "__main__":
    unittest.main()
