import itertools
import unittest
from fractions import Fraction

from screen import decision, read_curve


def brute(layers, k, free_cuda):
    keys = [(i, j, r) for i, (_, _, a, b) in enumerate(layers)
            for j, call in enumerate((a, b)) for r in call]
    best = {}
    for chosen in itertools.product((False, True), repeat=len(keys)):
        used = n = total = 0
        for i, (cpu, unknown, _, _) in enumerate(layers):
            used += max(0, sum(v for (il, _, _), v in zip(keys, chosen, strict=True)
                               if il == i) - unknown)
            for j in (0, 1):
                rest = [r for (il, call, r), held in zip(keys, chosen, strict=True)
                        if (i, j) == (il, call) and not held]
                n += int(bool(rest) and cpu)
                if cpu or not free_cuda:
                    total += max(sum(rest), 4 * max(rest, default=0))
        if used <= k:
            best[n] = min(total, best.get(n, total))
    return best


class TestTail(unittest.TestCase):
    def test_exhaustive_assignments(self):
        for prices in itertools.product((0, 2), repeat=5):
            a, b, c, d, e = prices
            for u in (0, 1, 3):
                layers = [(True, u, [a], [b, c]), (False, 0, [d], [e])]
                for k in range(4):
                    for free in (False, True):
                        self.assertEqual(read_curve(layers, k, free), brute(layers, k, free))

    def test_cutoff_can_change_optimal_placement(self):
        # Paying the small singleton costs less READ time but leaves two active groups.
        layers = [(True, 0, [2], [10, 7]), (False, 0, [], [])]
        curve = read_curve(layers, 1)
        self.assertEqual(curve, {1: 40, 2: 36})
        r = decision(curve, Fraction(1), Fraction(20))
        self.assertEqual(r["optimal_groups_at_zero"], [2])
        self.assertEqual(r["optimal_groups_at_cutoff"], [1])
        self.assertEqual(r["last_admissible_integer_us"], 10)
        self.assertEqual(r["first_excluding_integer_us"], 11)
        self.assertEqual(decision(curve, Fraction(4, 5), Fraction(20))
                         ["last_admissible_integer_us"], 12)

    def test_zero_cost_key_still_needs_compute(self):
        layers = [(True, 0, [0], []), (False, 0, [100], [])]
        self.assertEqual(read_curve(layers, 0, free_cuda=True), {1: 0})
        self.assertEqual(decision(read_curve(layers, 0), Fraction(1), Fraction(4))["status"],
                         "ALREADY_EXCLUDED_AT_ZERO")
        self.assertEqual(decision(read_curve(layers, 1, free_cuda=True), Fraction(1),
                                  Fraction(4))["status"], "NO_FINITE_CUTOFF")
        r = decision({1: 3}, Fraction(1), Fraction(3, 2))
        self.assertEqual(r["supremum_us"]["numerator"], 3)
        self.assertEqual(r["supremum_us"]["denominator"], 4)
        self.assertEqual(r["first_excluding_integer_us"], 1)
