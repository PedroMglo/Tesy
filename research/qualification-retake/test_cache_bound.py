import unittest
from functools import cache
from itertools import combinations, product

from cache_bound import minimum


def brute(groups, capacity, initial=None, eligible_initial=None):
    universe = frozenset().union(*groups)

    @cache
    def cost(index, resident):
        if index == len(groups):
            return 0
        pins = frozenset(groups[index])
        old = resident - pins
        keep = min(capacity - len(pins), len(old))
        return len(pins - resident) + min(
            cost(index + 1, pins.union(survivors)) for survivors in combinations(old, keep)
        )

    if initial is not None:
        return cost(0, frozenset(initial))
    if eligible_initial is not None:
        universe = universe.intersection(eligible_initial)
    return min(
        cost(0, frozenset(initial))
        for initial in combinations(universe, min(len(universe), capacity))
    )


class PinnedBelady(unittest.TestCase):
    def test_every_victim_and_warm_start_in_small_grouped_sequences(self):
        cohorts = list(combinations(range(4), 2)) + [(0,), (3,)]
        for groups in product(cohorts, repeat=3):
            for capacity in (2, 3, 4):
                self.assertEqual(minimum(groups, capacity), brute(groups, capacity))

    def test_fixed_start_with_unused_and_vacant_slots(self):
        for groups in product(((0, 1), (1, 2), (2, 3)), repeat=4):
            for state in ([], [0, 1], [1, 2, 99]):
                self.assertEqual(minimum(groups, 3, state), brute(groups, 3, state))

    def test_best_restricted_initial_residency(self):
        for groups in product(((0, 1), (1, 2), (2, 3), (0, 3)), repeat=4):
            for eligible in (set(), {2}, {1, 2, 3}, {0, 1, 2, 3, 4}):
                self.assertEqual(
                    minimum(groups, 2, eligible_initial=eligible),
                    brute(groups, 2, eligible_initial=eligible),
                )

    def test_refuse_unschedulable_or_duplicate_group(self):
        for group in ((0, 1, 2), (0, 0)):
            with self.assertRaisesRegex(ValueError, "pin set"):
                minimum([group], 2)
