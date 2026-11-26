"""Counterexamples for endpoints, bins and non-identifiability."""

import itertools
import unittest

import screen


class Prices(unittest.TestCase):
    def test_envelope_contains_assignments(self):
        ticks = [0, 200, 500, 1000, 1200]
        durations = [200, 300, 500, 200]
        for lags in itertools.product((0, 5), repeat=5):
            marks = [v - lag for v, lag in zip(ticks, lags, strict=True)]
            ds = [b - a for a, b in zip(marks[:-1], marks[1:], strict=True)]
            for mask in itertools.product((False, True), repeat=4):
                lo, hi = screen.constrained(durations, mask, sum(ds), 1, 5)
                exact = sum(d for d, included in zip(ds, mask, strict=True) if included)
                self.assertLessEqual(lo, exact)
                self.assertGreaterEqual(hi, exact)

    def test_order_and_clocks(self):
        data = screen.analysis(
            [0, 3000, 6000, 8000], [2000, 3100, 6200], list(screen.CLASSES), 9000
        )
        a, b = data["boundary_proxies"].values()
        self.assertEqual(a["parts"]["ordinary"]["sum_us"], 3000)
        self.assertEqual(b["parts"]["ordinary"]["sum_us"], 1100)
        self.assertFalse(data["sensitivity"][3]["compatible"])
        self.assertEqual(data["unconditional_proper_subset_native_us"], [0, 9000])

    def test_clock_not_strictly_monotonic(self):
        with self.assertRaises(ValueError):
            screen.stats([0, 1, 1], list(screen.CLASSES[:2]))

    def test_clock_unit(self):
        self.assertEqual(screen.clock_us((1, 2, 3, 4)), 62003004)
