import itertools
import unittest
from collections import OrderedDict
from pathlib import Path
from runpy import run_path

M = run_path(str(Path(__file__).with_name("score.py")))


class PolicyBounds(unittest.TestCase):
    def test_hits_then_sorted_misses(self):
        state = OrderedDict.fromkeys([0, 1, 2, 3])
        self.assertEqual(M["logical"](state, [3, 5, 1, 4, 3], 4), (2, 2, 2))
        self.assertEqual(list(state), [3, 1, 4, 5])

    def test_washout_for_every_order_and_membership(self):
        groups = [(3, 1), (2, 0), (4,), (6, 5), (0, 6)]
        cap = 3
        cut, forced, first = M["certify"](groups, cap)
        self.assertEqual(cut, 3)
        self.assertTrue(all(first))
        outputs = set()
        for n in range(cap + 1):
            for seed in itertools.permutations(range(7), n):
                state = OrderedDict.fromkeys(seed)
                fills = 0
                for i, group in enumerate(groups[: cut + 1]):
                    _, missing, _ = M["logical"](state, group, cap)
                    self.assertGreaterEqual(missing, forced[i])
                    fills += missing
                self.assertGreaterEqual(fills, 7 - cap)
                outputs.add(tuple(state))
        self.assertEqual(outputs, {(4, 5, 6)})

    def test_convergence_not_guessed_and_budget(self):
        self.assertIsNone(M["certify"]([(1,), (1,), (1,)], 2)[0])
        self.assertFalse(all(M["certify"]([(1,), (1,), (1,)], 2)[2]))
        p = M["prices"](1000, 47, 6)
        self.assertEqual(p["payload_bytes"], 13_219_200_000)
        self.assertFalse(p["exceeds_gross_link"])
