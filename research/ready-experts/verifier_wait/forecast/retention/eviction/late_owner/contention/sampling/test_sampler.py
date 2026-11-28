import unittest
from fractions import Fraction
from pathlib import Path
from runpy import run_path

S = run_path(Path(__file__).with_name("sampled.py"))


class SampleTests(unittest.TestCase):
    def test_inside_and_outside_bounds_run_on_the_supervisor_clock(self):
        # The last matching sample can finish after the worker has reached its barrier.
        self.assertEqual(S["bounds"]([2, 2, 4, 13, 19, 22], 17, True), (9, 17, 2))
        self.assertEqual(S["bounds"]([1, 2, 4, 2, 4, 7], 9, True), (0, 7, 1))
        self.assertEqual(S["bounds"]([0, 0, 0, 0, 0, 9], 7, True), (0, 7, 0))
        with self.assertRaises(ValueError):
            S["bounds"]([0, 0, 1, 0, 0, 9], 7, True)
        with self.assertRaises(ValueError):
            S["bounds"]([1, 0, 2, 0, 2, 7], 7, False)

    def test_ratio_encloses_regressions_and_missing_duration(self):
        self.assertEqual(
            S["interval_reduction"]([90, 100], [45, 50]), (Fraction(4, 9), Fraction(11, 20))
        )
        self.assertEqual(S["interval_reduction"]([0, 10], [10, 12]), (None, 0))
        self.assertEqual(S["median_lower"]([None, None, 1]), None)
        self.assertEqual(S["median_lower"]([None, 1, 2]), 1)

    def test_crossover_is_balanced_in_time_and_in_direction(self):
        rows = list(S["schedule"]())
        self.assertEqual(len(rows), 504)
        for stage in range(4):
            piece = [r for r in rows if r[0] == stage]
            self.assertEqual(sum(r[1] == 0 for r in piece), 62)
            self.assertEqual(sum(r[1] == 1 for r in piece), 62)
            self.assertEqual([piece[i][1] for i in (2, 4, 6, 8)], [0, 1, 1, 0])

    def test_graders_preserve_unobserved_lanes(self):
        pairs = {}
        for stage, order, p, h, t in S["schedule"]():
            key = (stage, order, p)
            clock = [100, 101, 110]
            if t and stage == 0:
                clock[0] = 104
            leg = [0, 50, 0] if h else [90, 100, 9]
            pairs.setdefault(key, {})[t if stage < 2 else h] = (clock, [leg])
        grade = S["class_grade"](pairs, 1)
        self.assertEqual(grade["observed_ppm"], [444444, 1000000])
        self.assertFalse(grade["neutral"])
        self.assertEqual(grade["reduction_ppm"], [0, 1000000])


if __name__ == "__main__":
    unittest.main()
