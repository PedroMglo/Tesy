import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screen import series  # noqa: E402


class ScreenTest(unittest.TestCase):
    def test_matched_arms_ratio_of_sums(self):
        r = series([1, 2, 1], [[2, 15, 8], [1, 20, 7], [2, 16, 8], [1, 12, 7]])
        one = r["1"]
        self.assertEqual(one["groups"], 2)
        self.assertAlmostEqual(one["pairs"][0]["gain_percent"], 20)
        self.assertAlmostEqual(one["pairs"][1]["gain_percent"], -25)
        self.assertAlmostEqual(one["median_gain_percent"], -2.5)
        self.assertEqual(one["pairs"][1]["positive_groups"], 0)
        self.assertTrue(one["any_positive"])
        self.assertFalse(one["both_positive"])
        self.assertEqual(r["2"]["logical_bytes"], 2 * 3 * 4_406_400)
        self.assertEqual(r["all"]["groups"], 3)

    def test_incomplete_vector_and_nonfinite_rejected(self):
        for bad in ([1], [float("nan"), 1], [2, 0]):
            with self.assertRaises(ValueError):
                series([1, 4], [[1, 2], [2, 4], [1, 1], bad])

    def test_wrong_stratum_or_cardinality_rejected(self):
        for bad in ([5], [True], [2], [0]):
            with self.assertRaises(ValueError):
                series(bad, [[1]] * 4)


if __name__ == "__main__":
    unittest.main()
