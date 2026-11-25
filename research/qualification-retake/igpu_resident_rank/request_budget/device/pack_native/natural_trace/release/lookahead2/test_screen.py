import itertools
import unittest
from functools import lru_cache
from pathlib import Path
from runpy import run_path

M = run_path(str(Path(__file__).with_name("screen.py")))


def brute(jobs):
    end = max(d for _, d, _ in jobs)

    @lru_cache(None)
    def best(t, left):
        if t == end:
            return 0
        value = best(t + 1, left)
        for i, (r, d, _) in enumerate(jobs):
            if r <= t < d and left[i]:
                new = list(left)
                new[i] -= 1
                value = max(value, 1 + best(t + 1, tuple(new)))
        return value

    return best(0, tuple(n for _, _, n in jobs))


class Tests(unittest.TestCase):
    def test_edf_is_exact_for_joint_capacity(self):
        variants = [(0, 1, 2), (0, 3, 2), (1, 3, 2), (2, 4, 1), (1, 1, 3), (3, 4, 2)]
        for jobs in itertools.product(variants, repeat=3):
            self.assertEqual(M["early_capacity"](jobs, 1, scale=1), brute(jobs))
        self.assertEqual(M["early_capacity"]([(0, 3, 2), (1, 3, 2)], 1, scale=1), 3)
        with self.assertRaises(ValueError):
            M["early_capacity"]([(1, 0, 1)], 1)

    def test_contracting_work_never_offers_waits_to_two_layers(self):
        c = M["contracted"]([(8, 10), (12, 17)])
        self.assertEqual(
            [c(t) for t in (6, 8, 9, 10, 11, 12, 15, 17, 20)], [6, 8, 8, 8, 9, 10, 10, 10, 13]
        )
        tasks = [(8, 12, 3), (10, 17, 4)]
        self.assertEqual(M["early_capacity"](tasks, 1, 1), 7)
        self.assertEqual(M["early_capacity"]([(c(r), c(d), n) for r, d, n in tasks], 1, 1), 2)

    def test_horizon_clipping_and_per_release_width(self):
        cells = [(1, 1, i) for i in range(3)]
        m = (
            dict(zip(cells, [5, 15, 35], strict=True)),
            dict(zip(cells, [10, 20, 40], strict=True)),
            dict(zip(cells, [[6], [16], [36]], strict=True)),
            {(1, 1): 1},
            [],
        )
        self.assertEqual(M["windows"]((1, 1, 0, -1), m, 2, "ranks_observed"), [])
        self.assertEqual(M["windows"]((1, 1, 1, -1), m, 2, "ranks_observed"), [(6, 15)])
        self.assertEqual(M["windows"]((1, 1, 2, 0), m, 2, "earliest_outer"), [(1, 35), (10, 35)])
        win = M["windows"]((1, 1, 2, 0), m, 2, "ranks_observed")
        self.assertEqual(list(M["batches"](win, 9, "four_per_horizon")), [(6, 35, 4), (16, 35, 4)])
        self.assertEqual(list(M["batches"](win, 9, "four_per_target")), [(6, 35, 4)])
        self.assertEqual(list(M["batches"](win, 9, "unlimited")), [(6, 35, 9)])
        m[2].pop(cells[0])
        with self.assertRaisesRegex(ValueError, "INCONCLUSIVE"):
            M["windows"]((1, 1, 1, -1), m, 1, "ranks_observed")

    def test_protect_decode_and_keep_the_two_budgets_disjoint(self):
        out = M["compute_budget"](18_000_000_000, 9_000_000_000, 6_000_000_000, 300_000_000)
        self.assertEqual(out["observed_margin_ns"], -2_300_000_000)
        self.assertEqual(out["margin_at_6_ns"], -1_133_333_333)
        self.assertAlmostEqual(out["min_decode_rate_for_both_outputs_per_s"], 47 / 6.7)


if __name__ == "__main__":
    unittest.main()
