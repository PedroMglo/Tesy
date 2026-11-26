"""Finite cache DP and event mutations independent of the C135 measurements."""

import unittest
from itertools import combinations, product

from screen import CUTS, bridge, optimum, reconstruct


def fixed_dp(initial, groups, capacity):
    costs = {frozenset(initial): 0}
    for group in map(frozenset, groups):
        following = {}
        for before, cost in costs.items():
            old = before - group
            for rest in combinations(old, min(len(old), capacity - len(group))):
                after = group.union(rest)
                score = cost + len(group - before)
                following[after] = min(following.get(after, score), score)
        costs = following
    return min(costs.values())


def event(kind, call=1, expert=-1, slot=-1, state=-1, victim=-1, gen=0):
    return dict(
        kind=kind,
        call_id=call,
        layer=0,
        expert=expert,
        slot=slot,
        state=state,
        victim=victim,
        generation=gen,
    )


class Proof(unittest.TestCase):
    def test_all_initials_and_all_simultaneous_waves(self):
        selections = [(0,), (1,), (2,), (0, 1), (0, 2), (1, 2)]
        starts = [[None, -1], [None, 2], [None, None], [-1, -1], [0, 1], [1, -1], [None, 6]]
        for slots, groups in product(starts, product(selections, repeat=3)):
            fixed = {x for x in slots if x is not None and x >= 0}
            ids = {0, 1, 2} - fixed
            best = min(
                fixed_dp(fixed.union(grant), groups, len(slots))
                for size in range(min(slots.count(None), len(ids)) + 1)
                for grant in combinations(ids, size)
            )
            result = optimum(slots, groups)
            self.assertEqual(result["wave_floor"], best)
            self.assertLessEqual(result["distinct_floor"], best)
        self.assertEqual(optimum([-1, 8], [(0, 1)])["maximum_initial_useful"], 0)

    def test_positive_witnesses_empty_and_unknown(self):
        rows = [
            event("CALL_BEGIN"),
            event("DEMAND", expert=1, slot=0, state=2),
            event("EVICT", expert=2, slot=1, state=2, victim=3),
            event("RESERVE", expert=3, slot=1),
            event("ENQUEUE", expert=3, slot=1, gen=8),
            event("RESERVE", expert=4, slot=2),
            event("CALL_END"),
            event("CALL_BEGIN", 2),
            event("CALL_END", 2),
            event("EVICT", 3, 1, 0, 2, 6),
            event("RESERVE", 3, 6, 0),
            event("EVICT", 3, 3, 1, 2, 5),
            event("RESERVE", 3, 5, 1),
            event("ENQUEUE", 3, 5, 1, gen=9),
        ]
        out = reconstruct(rows, n_layers=1, capacity=4)
        self.assertEqual(out[CUTS[0]], [[1, 2, -1, None]])
        self.assertEqual(out[CUTS[2]], [[1, 3, 4, None]])
        for index, bad in [
            (3, dict(expert=9)),
            (2, dict(state=1)),
            (12, dict(expert=7)),
            (13, dict(generation=12)),
            (4, dict(expert=2)),
            (5, dict(expert=3)),
        ]:
            with self.subTest(index=index, bad=bad), self.assertRaises(ValueError):
                altered = list(rows)
                altered[index] = {**rows[index], **bad}
                reconstruct(altered, n_layers=1, capacity=4)

    def test_bridge_including_first_wave_self_eviction(self):
        # R0 processes mandatory new expert 2 first, displacing initially needed
        # 1, then reads 1 again. The selected set is complete at the return.
        service = [
            event("RESERVE", expert=2),
            event("LOAD_END", expert=2),
            event("RESERVE", expert=1),
            event("LOAD_END", expert=1),
        ]
        r = bridge([0, 1], [1, 2], {1, 2}, service, [(0, 1)], [], 1)
        self.assertEqual(r["mandatory_call5"], 1)
        self.assertEqual(r["extra_historical_call5_loads"], 1)
        self.assertEqual(r["bridge_floor"], 1)
        for bad in (service[:-1], service + [event("PRELOAD", expert=2)]):
            with self.assertRaises(ValueError):
                bridge([0, 1], [1, 2], {1, 2}, bad, [(0, 1)], [], 1)
        self.assertEqual(bridge([None, 1], [None, 1], set(), [], [(1,)], [], 0)["bridge_floor"], 0)
        with self.assertRaises(ValueError):
            bridge([None, 1], [None, 1], set(), [], [(2,)], [event("DEMAND", 2, 2, 0, 1)], 1)


if __name__ == "__main__":
    unittest.main()
