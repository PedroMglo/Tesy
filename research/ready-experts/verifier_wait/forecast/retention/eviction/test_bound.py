"""Exercise the interval pricing proof independently of the 120B and its routes."""

import unittest
from itertools import combinations
from pathlib import Path
from runpy import run_path

B = run_path(Path(__file__).with_name("bound.py"))
Interval = B["R"]["Interval"]


class Bound(unittest.TestCase):
    def test_all_dag_paths_match_pipeline(self):
        costs = {
            (tile, stage): (tile * 7 + stage * 19) % 23 for tile in range(1, 6) for stage in (0, 1)
        }
        for path in B["paths"]():
            self.assertEqual(len(path), len(set(path)))
        expected = B["P"]["pipeline"]([(costs[t, 0], costs[t, 1]) for t in range(1, 6)])[-1][-1]
        self.assertEqual(expected, max(sum(costs[n] for n in path) for path in B["paths"]()))

    def test_nonlinear_rewards_at_shared_return(self):
        seq = [
            Interval(1, 8, 0, 0),
            Interval(3, 8, 0, 1),
            Interval(5, 10, 1, 2),
            Interval(9, 12, 1, 3),
            Interval(10, 12, 1, 4),
        ]

        def award(done):
            return sum(v.expert + 1 for v in done) + (11 if len(done) > 1 else 0)

        for cap in (0, 1, 2):
            optimum = 0
            for n in range(len(seq) + 1):
                for subset in combinations(seq, n):
                    if B["R"]["pressure"](subset) > cap:
                        continue
                    value = sum(
                        award([v for v in subset if v.end == end])
                        for end in {v.end for v in subset}
                    )
                    optimum = max(optimum, value)
            self.assertEqual(B["best"](seq, award, cap), optimum)


if __name__ == "__main__":
    unittest.main()
