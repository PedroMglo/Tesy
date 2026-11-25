import itertools
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screen import optimum


def brute(groups):
    universe = [key for g in groups for key, _ in g]

    def score(picked):
        floors = []
        for g in groups:
            remains = [v for key, v in g if key not in picked]
            floors.append(max([sum(remains) // 4, *remains]))
        return sum(floors)

    return [
        min(score(set(w)) for w in itertools.combinations(universe, n))
        for n in range(1 + len(universe))
    ]


class WarmMinimum(unittest.TestCase):
    def test_exhaustive_cardinalities_and_witnesses(self):
        for sizes in ((3, 2, 1), (5, 2), (6, 1, 1)):
            for seed in (0, 1, 2):
                gs = [
                    [((layer, x), 1 + ((layer * 13 + x * 3) * seed) % 5) for x in range(n)]
                    for layer, n in enumerate(sizes)
                ]
                frontier, pick = optimum(gs)
                self.assertEqual(frontier, brute(gs))
                for k, v in enumerate(frontier):
                    actual = set(pick(k))
                    self.assertEqual(len(actual), k)
                    rest = [[e for e in g if e[0] not in actual] for g in gs]
                    floor = sum(max([sum(t for _, t in g) // 4, *(t for _, t in g)]) for g in rest)
                    self.assertEqual(floor, v)
        self.assertEqual(optimum([])[0], [0])

    def test_tied_slowest_gang(self):
        gs = [[((0, x), 8) for x in (4, 0, 1)], [((1, 0), 3)]]
        f, pick = optimum(gs)
        self.assertEqual(f, [11, 8, 8, 3, 0])
        self.assertEqual(pick(1), [(1, 0)])
        self.assertEqual(pick(2), [(0, 0), (1, 0)])

    def test_arrival_keys_are_unique(self):
        with self.assertRaises(ValueError):
            optimum([[((1, 2), 3)], [((1, 2), 25)]])
