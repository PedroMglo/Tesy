import unittest
from pathlib import Path
from runpy import run_path

S = run_path(str(Path(__file__).with_name("score.py")))


class JointCostTest(unittest.TestCase):
    def test_same_key_charged_once_and_gap_saturation(self):
        r = S["charge"]({1, 2, 3}, {1}, [1, 2, 4, 9], {1, 2, 3, 4}, 50)
        self.assertEqual((r["union"], r["extra"], r["duplicate"], r["unused"]), (2, 1, 1, 1))
        self.assertEqual(r["residual_ns_8000000000"], 2 * 1652400 - 50)
        self.assertEqual(r["unbounded_ns_8000000000"], 1652400)

    def test_long_gap_cannot_hide_unpredicted_reads(self):
        r = S["charge"]({2, 5}, set(), [5], {2, 5}, 10**9)
        self.assertEqual(r["residual_ns_8000000000"], 1652400)
        with self.assertRaises(ValueError):
            S["charge"]({5}, set(), [5, 5], {5}, 1)


if __name__ == "__main__":
    unittest.main()
