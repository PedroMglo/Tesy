import itertools
import unittest
from pathlib import Path
from runpy import run_path

S = run_path(str(Path(__file__).with_name("score.py")))
SplitBank, Historical = S["SplitBank"], S["Q"]["POLICY"]["VictimBank"]


class PolicyTests(unittest.TestCase):
    def test_endpoints_at_every_prefix(self):
        for seq in itertools.product(range(3), repeat=5):
            for use in (False, True):
                old, new = Historical(2, use), SplitBank(2, 2 * use)
                for i, e in enumerate(seq):
                    rank = (0, 4, 5, 6) if i % 2 == 0 else (e, 7, 8, 9)
                    old.rank_row(0, rank)
                    new.rank(0, rank)
                    old.offer((0, e))
                    new.offer((0, e))
                    self.assertEqual(old.receipt(), new.summary())
                    self.assertEqual(sorted(old.held, key=old.held.get), list(new.held))

    def test_protection_and_loss(self):
        b = SplitBank(3, 1)
        b.rank(0, [0, 4, 5, 6])
        for e in (0, 1, 2, 3):
            b.offer((0, e))
        self.assertEqual(list(b.held), [(0, 0), (0, 2), (0, 3)])
        b.rank(0, [1, 5, 7, 8])
        b.rank(0, [1, 5, 7, 8])
        self.assertNotIn((0, 1), b.held)
        b.offer((0, 2))
        self.assertEqual(b.summary()["copies"]["CPU"], 4)
        b.offer((0, 1))
        self.assertEqual(list(b.held), [(0, 3), (0, 2), (0, 1)])

    def test_geometry_and_rank_validation(self):
        with self.assertRaises(ValueError):
            SplitBank(2, 3)
        for seq in ([0, 1, 1, 4], [-1, 1, 2, 3], [0, 1, 2, 128]):
            with self.assertRaises(ValueError):
                SplitBank(2, 1).rank(0, seq)


if __name__ == "__main__":
    unittest.main()
