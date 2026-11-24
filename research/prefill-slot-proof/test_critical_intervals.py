"""The time relaxation composes disjoint critical paths and overlapping capacity costs."""

import unittest

from critical_intervals import earliest_end


class ConsumerDeadlines(unittest.TestCase):
    def test_capacity_can_dominate_every_individual_service(self):
        points = {1: 0, 2: 5, 3: 55, 4: 60}
        # 5 jobs * 39 us minimum / 4 >= 48, then >=4 us of serial non-WAIT.
        self.assertEqual(earliest_end(points, {(2, 3)}, [(1, 3, 40)] * 5), 52)

    def test_sequential_consumer_deadlines_add(self):
        points = {1: 0, 2: 40, 3: 50, 4: 100}
        # Separate windows of 39 and 49 us, separated by >=9 us of work.
        self.assertEqual(earliest_end(points, {(1, 2), (3, 4)},
                                      [(1, 2, 40), (3, 4, 50)]), 97)

    def test_preload_can_advance_during_prior_compute(self):
        points = {1: 0, 2: 80, 3: 100}
        self.assertEqual(earliest_end(points, {(2, 3)}, [(1, 3, 40)]), 79)

    def test_rejects_an_interleaving_outside_the_controller_model(self):
        with self.assertRaisesRegex(ValueError, "inside WAIT"):
            earliest_end({1: 0, 2: 5, 3: 50}, {(1, 3)}, [])
