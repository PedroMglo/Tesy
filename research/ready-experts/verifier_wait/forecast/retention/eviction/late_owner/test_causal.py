"""Controls for online admission, delayed publication and equal-memory eviction."""

import unittest
from pathlib import Path
from runpy import run_path

Bank = run_path(Path(__file__).with_name("causal.py"))["Bank"]


class CausalBank(unittest.TestCase):
    def test_election_does_not_supply_a_page(self):
        bank = Bank(1, True)
        _, warm = bank.replay([[1, 1], [11, 9], [17, 9], [2, 1]], training=True)
        self.assertEqual((bank.elected, bank.ready, warm["T1_prefill"]["hits"]), ({9}, set(), 0))
        hits, sums = bank.replay([[1, 1], [11, 9], [17, 9], [11, 9], [17, 9], [2, 1]])
        self.assertEqual(hits, {2})
        self.assertEqual((sums["5"]["disk"], sums["5"]["captures"]), (1, 1))

    def test_return_with_pending_capture_cannot_reassign(self):
        bank = Bank(1, False)
        bank.replay([[1, 1], [11, 9], [17, 9], [2, 1]])
        hits, sums = bank.replay(
            [
                [1, 1],
                [11, 9],
                [11, 2],
                [17, 2],
                [2, 0],
                [17, 9],
                [1, 2],
                [11, 9],
                [17, 9],
                [11, 2],
                [17, 2],
                [2, 1],
            ]
        )
        self.assertEqual((hits, bank.elected, bank.ready), ({3}, {2}, set()))
        self.assertEqual(sums["148"]["evictions"], 1)
        self.assertEqual(sums["5"]["drains"], 0)

    def test_same_capacity_different_observable_information(self):
        history = [[1, 1], [11, 9], [17, 9], [11, 9], [17, 9], [11, 2], [17, 2], [2, 1]]
        for frequency, winner in ((True, 9), (False, 2)):
            bank = Bank(1, frequency)
            bank.replay(history)
            self.assertEqual(bank.elected, {winner})
            with self.assertRaisesRegex(ValueError, "publication without reservation"):
                bank.replay([[1, 1], [17, winner], [2, 1]])


if __name__ == "__main__":
    unittest.main()
