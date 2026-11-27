import itertools
import unittest
from pathlib import Path
from runpy import run_path

E = run_path(str(Path(__file__).resolve().parents[1] / "research/ready-experts/existence.py"))


class EveryBankBound(unittest.TestCase):
    def test_all_subsets_both_clocks_and_both_supporting_branches(self):
        call, job = E["BASE"]["Call"], E["R"]["Job"]
        calls = [
            call(1, 16, 12, 0, 0, 0),
            call(2, 30, 10, 0, 0, 0),
            call(3, 20, 18, 0, 0, 0),
            call(47, 17, 15, 0, 0, 0),
        ]
        keys = [(0, i) for i in range(5)]
        groups = {
            1: {(1, 0): [job(k, 3, 1) for k in keys]},
            2: {(1, 0): [job(keys[4], 10, 0)]},
            3: {(1, 0): [job(keys[1], 4, 3), job(keys[1], 3, 4), job(keys[2], 7, 0)]},
            47: {(1, 0): [job(keys[3], 10, 2), job(keys[0], 2, 1)]},
        }
        model = (calls, groups, {"first_final": 1, "decode": 4})
        base = E["R"]["bounds"](*model)
        scores = E["supporting_credit"](calls, groups)
        count = {"first_final": 3, "decode": 2}
        for n in range(len(keys) + 1):
            for selection in itertools.combinations(keys, n):
                row = E["R"]["bounds"](*model, bank=set(selection))
                for k in count:
                    gain = base[k] - row[k]
                    self.assertGreaterEqual(gain, 0)
                    self.assertLessEqual(gain, E["upper_ns"](scores[k], selection, n, count[k]))
                    self.assertLessEqual(gain, E["upper_ns"](scores[k], keys, n, count[k]))
        self.assertIn(keys[0], scores["first_final"])
        self.assertNotIn(keys[0], scores["decode"])


if __name__ == "__main__":
    unittest.main()
