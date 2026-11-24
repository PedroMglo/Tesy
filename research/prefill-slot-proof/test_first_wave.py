import unittest

from first_wave import rank_winner


class TestHistoricalRank(unittest.TestCase):
    def test_minimum_survives_in_a_smaller_candidate_set(self):
        # Slots 2 and 4 have the same hotness and recency in this fixture.
        # The historical winner on the inclusive set incorporates index 2.
        observed = [(100, {2, 4, 8}, 2), (110, {4, 8}, 4)]
        self.assertEqual(rank_winner({2, 4}, observed), (100, 2))
        self.assertEqual(rank_winner({4, 8}, observed), (110, 4))

    def test_partial_or_contradictory_observation(self):
        with self.assertRaises(ValueError):
            rank_winner({2, 4}, [(100, {1, 2, 4}, 1), (110, {2}, 2)])
        with self.assertRaises(ValueError):
            rank_winner({2, 4}, [(100, {2, 4}, 2), (110, {2, 4}, 4)])
