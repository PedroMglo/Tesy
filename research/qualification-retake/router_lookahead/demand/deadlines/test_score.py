"""Check whole-read scheduling against exhaustive tiny schedules; validate demand-wave identity."""

import itertools
import unittest
from pathlib import Path
from runpy import run_path

S = run_path(str(Path(__file__).with_name("score.py")))
NANO = S["NANO"]


class Tests(unittest.TestCase):
    def test_cardinality_against_exhaustive(self):
        for gaps in itertools.product((0, 1, 2, 3, 4), repeat=3):
            opt = 0
            for length in range(1, 4):
                for chosen in itertools.permutations(gaps, length):
                    if all((i + 1) * 2 * NANO <= d * (2 * NANO) for i, d in enumerate(chosen)):
                        opt = max(opt, length)
            self.assertEqual(S["max_completions"](gaps, 2 * NANO, 2), opt)
        self.assertEqual(S["max_completions"]([3], NANO - 1, 3), 0)
        self.assertEqual(S["max_completions"]([3], NANO, 3), 1)

    def test_false_issues_queue_across_releases(self):
        sites = [
            (1, 10, "prefill/CPU", [8, 9], {9: (12, 12, 12)}),
            (2, 13, "prefill/CPU", [2], {2: (16, 16, 16)}),
        ]
        r = S["evaluate"](sites, NANO, window=3)
        self.assertEqual(r["by_target"]["prefill/CPU"]["barrier_fifo"], 0)
        self.assertEqual(r["by_target"]["prefill/CPU"]["barrier_oracle"], 1)
        self.assertEqual(r["sites_overlapping_previous_deadlines"]["barrier"], 0)

    def test_preload_reserve_and_consume_are_different_waves(self):
        Row = S["M"]["AUDIT"]["pfj"]["Row"]

        def r(kind, ns, wave):
            return Row(ns, 0, 1, 0, 0, 0, kind, 1, 1, wave, 2, 3, 4, 0, -1, -1, 0, 0)

        e = [r(k, n, 0) for n, k in enumerate((9, 11, 12, 19, 20, 23, 13, 30, 17), 1)]
        e += [r(k, n, 1) for n, k in enumerate((9, 10, 19, 20, 23), 10)]
        ds = S["job_deadlines"](e)
        self.assertEqual(ds[(2, 4, 1, 3)], ((1, 1, 2, 1), (2, 7, 12)))
        with self.assertRaises((ValueError, AssertionError)):
            S["job_deadlines"](e[:2] + e[3:])
        with self.assertRaises((ValueError, AssertionError)):
            S["job_deadlines"](e[:8] + e[9:] + [e[8]._replace(ns=16)])


if __name__ == "__main__":
    unittest.main()
