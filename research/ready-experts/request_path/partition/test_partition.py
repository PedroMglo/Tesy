"""Model-free checks on the optimisation and the temporal boundary."""

import itertools
import sys
import unittest
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import policy as p  # noqa: E402


def exact(groups, initial, capacity, restore):
    @lru_cache(None)
    def visit(i, current):
        if i == len(groups):
            return len(set(restore).difference(current))
        now = set(groups[i])
        pool = set(current) | now
        debit = len(now.difference(current))
        feasible = itertools.combinations(sorted(pool), min(capacity, len(pool)))
        return debit + min(visit(i + 1, state) for state in feasible)

    return visit(0, tuple(initial))


class FramePolicyTests(unittest.TestCase):
    def test_oracle_against_exhaustive_replacement_and_terminal_demand(self):
        possible = ((0, 1), (1, 2), (2,), (3, 0))
        for groups in itertools.product(possible, repeat=3):
            for cap in (0, 1, 2):
                initial = tuple(range(cap))
                for target in ((), tuple(reversed(initial))):
                    waves = [p.Wave(i, 1, 0, 0, keys) for i, keys in enumerate(groups)]
                    counts, _ = p.ideal(waves, initial, cap, lambda n: "test", target)
                    self.assertEqual(sum(counts.values()), exact(groups, initial, cap, target))

    def test_hits_are_checked_before_any_member_of_a_wave_is_evicted(self):
        waves = [p.Wave(1, 1, 0, -1, (0, 1, 2, 3))]
        curve, _ = p.curves(waves, [3])
        self.assertEqual(curve[0][1], 1)
        self.assertEqual(curve[0][0], 0)

    def test_nonconcave_curve_and_documented_tie(self):
        self.assertEqual(p.allocate([[0, 0, 7], [0, 2, 3]], 2), ([2, 0], 7))
        self.assertEqual(p.allocate([[0, 1], [0, 1]], 1), ([1, 0], 1))

    def test_empty_waves_and_direct_order(self):
        ranks = [3, 2, 1, 0] * 32
        scheduled = p.waves({(1, 1, 0): ranks, (2, 1, 0): ranks[:4]})
        self.assertEqual(len(scheduled), 9)
        self.assertEqual(sum(not w.keys for w in scheduled), 7)
        self.assertEqual(scheduled[-1].keys, (3, 2, 1, 0))
        with self.assertRaisesRegex(ValueError, "top four"):
            p.waves({(1, 1, 0): [0, 1, 1, 2]})


if __name__ == "__main__":
    unittest.main()
