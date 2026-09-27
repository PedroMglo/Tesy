"""Discriminate the frozen paired-gain definition from ratio-of-medians."""

import statistics
import unittest

from c2_gate import GateError
from c7_timing_gate import gain


class PairedGain(unittest.TestCase):
    def test_median_of_pair_gains(self):
        pairs = [(100.0, 90.0), (1000.0, 1000.0)]
        self.assertEqual(statistics.median(gain(p8, p12) for p8, p12 in pairs), 5.0)
        self.assertNotEqual(gain(statistics.median(p8 for p8, _ in pairs),
                                 statistics.median(p12 for _, p12 in pairs)), 5.0)

    def test_invalid_denominator_and_nonfinite(self):
        for pair in ((0, 1), (-1, 1), (1, float("inf"))):
            with self.subTest(pair=pair), self.assertRaises(GateError):
                gain(*pair)
