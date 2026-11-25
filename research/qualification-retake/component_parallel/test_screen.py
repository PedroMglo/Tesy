"""Independent exhaustive assignments. No journal or model access."""

import itertools
import random
import unittest

from screen import score, solve


def brute(tasks):
    """Enumerate every placement, identifying permutations of equivalent workers."""
    states = {(0, 0, 0, 0)}
    for w in tasks:
        next_step = set()
        for s in states:
            for lane in range(4):
                v = list(s)
                v[lane] += w
                next_step.add(tuple(sorted(v)))
        states = next_step
    return min(s[-1] for s in states)


class ComponentParallel(unittest.TestCase):
    def check(self, jobs):
        value, lanes = solve(jobs)
        self.assertEqual(value, brute(jobs))
        self.assertEqual(len(lanes), 4)
        self.assertEqual(sorted(itertools.chain.from_iterable(lanes)), list(range(len(jobs))))
        self.assertEqual(max(sum(jobs[i] for i in lane) for lane in lanes), value)
        return value

    def test_small_all_multisets(self):
        for n in range(9):
            for jobs in itertools.combinations_with_replacement((0, 2, 3), n):
                self.check(jobs)

    def test_two_to_four_misses_against_enumeration(self):
        seq = random.Random(304)
        for cnt in (6, 9, 12):
            for _ in range(7):
                self.check([seq.randrange(14) for _ in range(cnt)])

    def test_lpt_can_be_suboptimal(self):
        # LPT gives 11: an exact four-way partition into tens exists.
        jobs = [7, 7, 6, 5, 4, 3, 3, 3, 2]
        value = self.check(jobs)
        self.assertEqual(value, 10)
        result = [0] * 4
        for i in sorted(jobs, reverse=True):
            result[result.index(min(result))] += i
        self.assertGreater(max(result), value)

    def test_a_single_generation_and_three_identical_jobs(self):
        self.assertEqual(self.check([4, 7, 12]), 12)
        self.assertEqual(self.check([9] * 12), 27)
        self.assertEqual(self.check([0] * 12), 0)
        for bad in ([1] * 13, [1, -1], [True], [2.0]):
            with self.assertRaises(ValueError):
                solve(bad)

    def test_wall_cost_and_logical_bandwidth(self):
        one = score(5_000_000, 333_333, 5_000_001)
        self.assertTrue(one["scales"]["1"]["reaches"])
        self.assertLess(one["scales"]["1"]["additional_cost_allowed_s"], 0.000001)
        self.assertEqual(one["required_payload_B_per_s"], 1_000_001)
        two = score(5_000_001, 333_333, 5_000_001)
        self.assertFalse(two["scales"]["1"]["reaches"])
        self.assertGreater(two["scales"]["1"]["excess_s"], 0)
        self.assertTrue(two["scales"]["0.8"]["reaches"])
        self.assertIsNone(score(0, 5_333_334, 5)["required_payload_B_per_s"])


if __name__ == "__main__":
    unittest.main()
