import unittest
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

S = run_path(str(Path(__file__).with_name("screen.py")))


class Scope(unittest.TestCase):
    def test_target_mask(self):
        keys = [(1, 0), (1, 1), (2, 24), (2, 25), (3, 1), (48, 24)]
        jobs = {k: SimpleNamespace(site=(k[0], 1, k[1], 0)) for k in keys}
        choices = dict.fromkeys(keys, "pack")
        choices[1, 1] = "bank"
        got = S["include"](choices, jobs, True)
        self.assertEqual(
            {k: v for k, v in got.items() if v != "outside_subset"},
            {(1, 1): "bank", (2, 24): "pack"},
        )
        other = S["include"](choices, jobs, False)
        self.assertTrue(all((got[k] == src) != (other[k] == src) for k, src in choices.items()))

    def test_one_shared_link_and_fail_on_amount_changes(self):
        l_tasks = defaultdict(list, {1: [(0, 10, 8)]})
        r_tasks = defaultdict(list, {1: [(0, 10, 8)]})
        a = l_tasks, Counter({1: 8}), Counter()
        b = r_tasks, Counter({1: 8}), Counter()
        together = S["merge_parts"](a, b, Counter({1: 16}))
        self.assertEqual(S["L"]["early_capacity"](together[1], 1, 1), 10)
        with self.assertRaisesRegex(ValueError, "payload"):
            S["merge_parts"](a, b, Counter({1: 17}))


if __name__ == "__main__":
    unittest.main()
