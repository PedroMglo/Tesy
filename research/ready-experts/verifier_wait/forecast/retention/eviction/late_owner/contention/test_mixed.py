"""Test the time before a hit and after the hit has stopped."""

import unittest
from pathlib import Path
from runpy import run_path

M = run_path(Path(__file__).with_name("mixed.py"))
DEPTH = run_path(Path(__file__).with_name("depths.py"))


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


class PriceTests(unittest.TestCase):
    def test_one_hit_order_and_per_job_exposure(self):
        rows = [read(0, 0, 10), read(1, 2, 5), read(2, 3, 7)]
        candidates, areas = DEPTH["classify"](rows, {1})
        self.assertEqual(candidates["3/1"], {(2, 3, 1)})
        self.assertEqual(areas[2], {"2/1": 1, "3/1": 2})
        self.assertEqual(areas[3], {"2/1": 2, "3/1": 2})

    def test_one_surviving_lane_and_failed_neutrality(self):
        plan = dict(labels=["2/1"], pack_stat=[1, 2, 3, 4, 5], expected_records=182)
        lines = ["fd 1 2 3 4 5"]
        for stage, order, p, hit, trace in DEPTH["schedule"]():
            cost = 120 - 30 * hit
            gate = cost + 20 * (trace and stage == 1)
            clocks = (
                ([10, cost - 10] + ([10, 80] if not hit else [0, 0]) + [0] * 4)
                if trace
                else [0] * 8
            )
            row = [0, stage, order, p, hit, trace, gate, gate + 50, gate + 100, *clocks]
            lines.append("row " + " ".join(map(str, row)))
        lines += ["closed 0 121 61 0 0 363 363 0 0", "drained"]
        out = DEPTH["parse"](lines, plan)["classes"]["2/1"]
        self.assertFalse(out["neutral"])
        self.assertEqual(out["reduction_ppm"], [0, 1_000_000])
        self.assertEqual(out["median_lane_reduction"], [[3, 10], [3, 10]])
        lines[-2] = lines[-2].replace("61", "60")
        with self.assertRaises(ValueError):
            DEPTH["parse"](lines, plan)


if __name__ == "__main__":
    unittest.main()
