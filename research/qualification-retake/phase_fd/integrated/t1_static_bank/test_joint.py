import importlib.util
import itertools
import unittest
from collections import Counter
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "fixed_bank_joint", Path(__file__).with_name("joint.py")
)
j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(j)


class Joint(unittest.TestCase):
    def setUp(self):
        self.keys = [(0, i) for i in range(6)]
        self.v = Counter(dict(zip(self.keys, (3, 13, 1, 9, 24, 8), strict=True)))
        self.h = Counter(dict(zip(self.keys, (7, 1, 13, 2, 1, 8), strict=True)))
        self.groups = [
            [(self.keys[0], 13), (self.keys[1], 11), (self.keys[2], 10)],
            [(self.keys[3], 19)],
        ]
        self.opts = j.options(self.groups, set(self.keys), self.v, self.h)

    def test_integer_certificates(self):
        for required, hits in ((13, 3), (12, 9), (32, 40)):
            for prices in ((1, 2, 1, 1), (22, 300, 55, 1), (17, 0, 0, 220), (1, 3, 19, 32)):
                upper = j.certificate(self.opts, 2, required, hits, prices)
                for keys in itertools.combinations(self.keys, 2):
                    if (
                        sum(self.v[k] for k in keys) >= required
                        and sum(self.h[k] for k in keys) >= hits
                    ):
                        gain = sum(
                            j.bank.opportunity.floor([t for _, t in g])
                            - j.bank.opportunity.floor([t for k, t in g if k not in keys])
                            for g in self.groups
                        )
                        self.assertGreaterEqual(upper, gain)
                simple = j.simple(set(self.keys), self.v, self.h, 2, required, hits)
                self.assertGreaterEqual(
                    simple["upper"],
                    max(
                        sum(self.v[k] + simple["hit_price"] * self.h[k] for k in s)
                        for s in itertools.combinations(self.keys, 2)
                    ),
                )

    def test_joint_rc_and_external_candidates(self):
        if not j.SOLVER.is_file() or j.src.sha(j.SOLVER) != j.SOLVER_SHA:
            self.skipTest("optional pinned solver absent")
        vals, dual, status = j.solve_lp(self.opts, 2, 10, 8)
        self.assertEqual(status, "EXIT_0")
        self.assertTrue(vals)
        self.assertTrue(any(j.rounding(self.opts, vals)))
        vals, _, status = j.solve_lp(self.opts, 2, 10, 8, 3)
        self.assertIn(status, ("EXIT_0", "EXIT_1"))
        self.assertTrue(
            any(
                len(keys) <= 2
                and sum(self.v[k] for k in keys) >= 10
                and sum(self.h[k] for k in keys) >= 8
                for keys in j.rounding(self.opts, vals)
            )
        )
        self.assertTrue(all(v >= 0 for v in dual))

    def test_boundary(self):
        for den in (1, 5):
            a = 1 if den == 1 else 4
            for slack in range(25):
                t = 10**10 - slack
                limit = j.max_residual(t, a, den)
                self.assertLessEqual(t + a * limit // den, 10**10)
                self.assertGreater(t + a * (limit + 1) // den, 10**10)

    def test_group_repetition(self):
        with self.assertRaises(ValueError):
            j.options(self.groups * 2, set(self.keys), self.v, self.h)


if __name__ == "__main__":
    unittest.main()
