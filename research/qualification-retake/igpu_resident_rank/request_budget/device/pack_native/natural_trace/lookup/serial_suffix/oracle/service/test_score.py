import itertools
import random
import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

M = run_path(str(Path(__file__).with_name("score.py")))
Event = M["Event"]


class TestService(unittest.TestCase):
    def test_each_certificate_dominates_the_exhaustive_price_optimum(self):
        rng = random.Random(261125)
        offered = set(range(6))
        ev = []
        for _ in range(25):
            sources = frozenset(rng.sample(sorted(offered), rng.randint(1, 5)))
            jobs = tuple(
                (rng.choice(sorted(sources) + [6, 7]), rng.randrange(1, 60)) for _ in range(8)
            )
            ev.append(Event(400, sources, jobs, "prefill"))
        for s, cap in ((0, 1), (500_000, 2), (791_011, 2), (1_000_000, 3)):

            def score(selected, price=s):
                rows, _ = M["cost_rows"](ev, set(selected), offered)
                return M["exact"](rows, price)

            optimal = max(score(x) for x in itertools.combinations(offered, cap))
            for value in M["certificate"](ev, offered, [0, 2, 5], s, cap).values():
                self.assertGreaterEqual(value, optimal)

    def test_never_offered_floors_and_rounding(self):
        ev = [Event(81, frozenset({1}), ((1, 64), (8, 7), (4, 33)), "prefill")]
        fixed, counters = M["cost_rows"](ev, {1}, {1})
        self.assertEqual(fixed, [(81, 33)])
        self.assertEqual(counters["uncovered_never_offered_jobs"], 2)
        self.assertEqual(M["exact"](fixed, 500_000), 65)
        self.assertEqual(M["exact"](fixed, 1_000_000), 48)
        self.assertEqual(min(M["certificate"](ev, {1}, [1], 1_000_000, 1).values()), 48)
        self.assertEqual(M["cost_rows"](ev, {2}, {1})[0], [])

    def test_removed_hit_can_propagate_only_until_drain(self):
        def wave(layer, expert, start_drained, end_drained):
            key = (layer, 0, 1, expert)
            return SimpleNamespace(
                site=(3, 0, layer, 0),
                start=0,
                end=50,
                reserved={key},
                demands={key},
                required_service={key: 31},
                start_drained=start_drained,
                end_drained=end_drained,
            )

        seq = [wave(1, 3, True, False), wave(25, 2, False, True), wave(26, 8, True, True)]
        out = M["events"](seq, ["prefill", "prefill", "anchor"], {(1, 3)}, True)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].jobs, (((25, 2), 31),))
        self.assertEqual(M["cost_rows"](out, {(1, 3)}, {(1, 3)})[0], [(50, 31)])

    def test_threshold_integer_grid(self):
        result = M["threshold"](lambda x: 3 - (x * 10 // 1_000_000))
        self.assertEqual(result, {"max_feasible_ppm": 399_999, "first_infeasible_ppm": 400_000})
        self.assertIsNone(M["threshold"](lambda x: -1)["max_feasible_ppm"])
        self.assertIsNone(M["threshold"](lambda x: 0)["first_infeasible_ppm"])


if __name__ == "__main__":
    unittest.main()
