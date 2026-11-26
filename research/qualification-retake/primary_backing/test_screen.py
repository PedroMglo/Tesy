"""Integer clocks for a demand-only primary cache. No recordings are opened."""

import unittest

from screen import Inconclusive, classify, contribution, score


class BackingTest(unittest.TestCase):
    def test_known_hit_disappears_with_whole_job(self):
        seen = {1, 4}
        work = {
            1: [(11, 41), (42, 61), (63, 90)],
            2: [(10, 17), (21, 27), (30, 37)],
            3: [(11, 17), (22, 27), (31, 38)],
        }
        result = contribution(seen, [1, 2, 3, 4], work, (15, 35))
        self.assertEqual(result["all_read_floor_us"], 73)
        self.assertEqual(result["required_read_floor_us"], 17)
        self.assertEqual(result["union_outside_wait_us"], 8)
        self.assertEqual(result["required"], 2)
        self.assertEqual(seen, {1, 2, 3, 4})
        self.assertEqual(contribution(seen, [1, 2, 3, 4], work, None)["required"], 0)

    def test_uncounted_reads_are_invalid(self):
        for work in ({}, {4: [(4, 9), (8, 11), (13, 17)]}, {4: [(4, 9), (10, 11)]}):
            with self.subTest(work=work), self.assertRaises(Inconclusive):
                contribution({1, 2, 3}, [1, 2, 3, 4], work, None)

    def test_outside_wait_covers_whole_frequency_when_no_wait(self):
        work = {4: [(10, 15), (20, 25), (30, 35)]}
        v = contribution({1, 2, 3}, [1, 2, 3, 4], work, None)
        self.assertEqual(v["union_outside_wait_us"], 15)
        self.assertEqual(v["required_read_floor_us"], 12)

    def test_conditional_label_and_threshold(self):
        def result(read, fixed):
            return {
                "arm": {
                    "scale": {
                        k: {"read": score(read, 0, n, d), "with_fixed": score(read, fixed, n, d)}
                        for k, n, d in [("1", 1, 1), ("0.8", 4, 5)]
                    }
                }
            }

        self.assertEqual(classify(result(7_000_000, 0)), "NO_GO_PRIMARY_BACKING_FIXED_READ")
        self.assertEqual(
            classify(result(6_000_000, 1_000_000)), "NO_GO_CONDITIONAL_FIXED_REMAINDER"
        )
        self.assertEqual(classify(result(6_000_000, 200_000)), "INCONCLUSIVE")
        self.assertFalse(score(16_000_000, 0, 1, 3)["excludes"])
