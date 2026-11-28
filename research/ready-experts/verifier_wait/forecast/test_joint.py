"""Checks for the compositional confidence certificate."""

import unittest
from pathlib import Path
from runpy import run_path

J = run_path(Path(__file__).resolve().with_name("joint.py"))


class ConfidenceTests(unittest.TestCase):
    def test_same_correct_and_same_wrong_read_coalesce_at_the_boundary(self):
        ref = [[[[0, 0], [2, 1]]]]
        offers = [(27, 0, 0, 1, 1), (27, 0, 0, 0, 1), (27, 0, 0, 2, 0)]
        self.assertEqual(J["materialize"](ref, offers, True, 27), [[[3, 3]]])
        self.assertEqual(J["materialize"](ref, offers, False, 27), [[[3, 3]]])
        self.assertEqual(J["materialize"](ref, offers, True, 28), [[[2, 1]]])
        self.assertEqual(J["materialize"](ref, offers, False, 28), [[[0, 0]]])

    def test_disjoint_pass_ranges_are_preserved(self):
        result = []
        for a, b in [(101, 140), (100, 100), (25, 63), (0, 24)]:
            J["merge_descending"](result, a, b)
        self.assertEqual(result, [[100, 140], [0, 63]])

    def test_same_layer_cannot_forecast_a_cold_record_twice(self):
        layer = [[120, 1, 1], [90, 1, 0]]
        with self.assertRaises((ValueError, RuntimeError, AssertionError)):
            J["events"]([[layer] + [[] for _ in range(35)]])


if __name__ == "__main__":
    unittest.main()
