"""Check parking capacity, return boundaries, and the pair-credit relaxation."""

import unittest
from itertools import combinations
from pathlib import Path
from runpy import run_path

M = run_path(Path(__file__).with_name("replay.py"))
Interval = M["Interval"]


class Parking(unittest.TestCase):
    def test_exchange_rule_matches_exhaustive_subsets_including_ties(self):
        spans = [(0, 3), (0, 2), (0, 2), (1, 4), (2, 3), (3, 5), (2, 5), (4, 5)]
        ivs = [Interval(a, b, 0, e) for e, (a, b) in enumerate(spans)]
        for cap in (0, 1, 2, 4):
            exact = max(
                n
                for n in range(len(ivs) + 1)
                for test in combinations(ivs, n)
                if M["pressure"](test) <= cap
            )
            self.assertEqual(len(M["maximum"](ivs, cap)), exact)

    def test_bank_hit_can_seed_but_cannot_redeem_a_read_or_cross_return(self):
        sites = {
            (1, 0, 0): [(17, False)],
            (2, 1, 0): [(17, False), (9, True), (4, False)],
            (2, 2, 0): [(17, False), (9, False), (4, True)],
        }
        _, eligible, best, causal, caps = M["opportunities"](sites)
        self.assertEqual({i.expert for i in eligible}, {17, 9})
        self.assertEqual(len(best), 2)
        self.assertEqual({i.expert for i in causal}, {9})
        self.assertEqual(caps, [7, 0])

    def test_breaking_an_original_adjacent_pair_keeps_optimistic_credit(self):
        work = [[3, 100, 10], [4, 80, 9], [7, 40, 7]]
        raw = dict(calls=[], groups=[[2, 1, 0, 1, 2, 3, 4, work]])
        new = M["grant_original_pairs"](raw, {}, [list(range(128))])
        self.assertEqual(new["groups"][0][-1], [[3, 0, 10], [4, 0, 9], [7, 40, 7]])
        self.assertEqual(work[0], [3, 100, 10])


if __name__ == "__main__":
    unittest.main()
