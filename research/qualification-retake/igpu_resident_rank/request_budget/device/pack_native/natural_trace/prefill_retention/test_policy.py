import unittest
from pathlib import Path
from runpy import run_path

Bank = run_path(str(Path(__file__).with_name("policy.py")))["VictimBank"]


class RetentionTest(unittest.TestCase):
    def test_scores_only_move_bytes_on_eligible_offer(self):
        b = Bank(2, True)
        b.offer((0, 1))
        b.offer((0, 2))
        b.offer((0, 3))
        self.assertNotIn((0, 1), b.held)
        for _ in range(3):
            b.rank_row(0, [1, 2, 4, 5])
        self.assertNotIn((0, 1), b.held)
        b.offer((0, 1))
        self.assertEqual(set(b.held), {(0, 1), (0, 2)})
        b.offer((25, 7))
        self.assertEqual(b.receipt()["rejected"], 1)
        self.assertEqual(b.receipt()["copies"], {"CPU": 4, "CUDA0": 0})

    def test_control_updates_offer_recency_without_recapture(self):
        b = Bank(2, False)
        b.offer((0, 1))
        b.offer((25, 2))
        b.offer((0, 1))
        b.rank_row(25, [2, 3, 4, 5])
        b.offer((25, 9))
        self.assertEqual(set(b.held), {(0, 1), (25, 9)})
        self.assertEqual(b.receipt()["copies"], {"CPU": 1, "CUDA0": 2})
        self.assertEqual(b.receipt()["repeated"], 1)
        with self.assertRaises(ValueError):
            b.rank_row(0, [0, 0, 1, 2])


if __name__ == "__main__":
    unittest.main()
