import itertools
import unittest
from functools import lru_cache
from pathlib import Path
from runpy import run_path

bounds = run_path(str(Path(__file__).with_name("bounds.py")))["bounds"]


class TestPhaseIO(unittest.TestCase):
    def test_delayed_read_and_timestamp(self):
        # Both reads might have happened before phase [5, 9]. Counting final
        # timestamps 4 and 8 as exact read times would misattribute the jump.
        self.assertEqual(bounds([(1, 4, 100), (4, 8, 150)], 50, 5, 9, 0), [0, 50])
        self.assertEqual(bounds([(4, 5, 102), (6, 7, 125)], 40, 3, 8, 0), [23, 40])
        self.assertEqual(bounds([(4, 5, 102), (6, 7, 125)], 40, 3, 8, 6), [0, 40])

    def test_foreign_baseline_and_endpoints(self):
        self.assertEqual(bounds([(1, 2, 100), (8, 9, 117)], 24, 3, 7, 0), [0, 17])
        self.assertEqual(bounds([], 24, 3, 7, 0), [0, 24])
        with self.assertRaises(ValueError):
            bounds([(1, 2, 100), (8, 9, 99)], 24, 3, 7, 0)
        with self.assertRaises(ValueError):
            bounds([(1, 2, 100), (8, 9, 117)], 16, 3, 7, 0)

    def test_small_exact_schedules_are_inside_bounds(self):
        # Independent exhaustive simulator: choose arrival ticks for two bytes,
        # both read times within their collection windows, and a common origin
        # offset. The first/last counters are never assumed to be absolute zero.
        cached = lru_cache(maxsize=None)(bounds)
        for ticks in itertools.combinations_with_replacement(range(9), 2):
            for t1, t2 in itertools.product(range(1, 4), range(4, 7)):
                observations = (
                    (1, 3, 80 + sum(t <= t1 for t in ticks)),
                    (4, 6, 80 + sum(t <= t2 for t in ticks)),
                )
                lo, hi = cached(observations, 2, 2, 5, 2)
                for shift in range(3):
                    real = sum(2 + shift < t <= 5 + shift for t in ticks)
                    self.assertLessEqual(lo, real)
                    self.assertLessEqual(real, hi)


if __name__ == "__main__":
    unittest.main()
