import unittest

from timing import lower_bound


class TimingTests(unittest.TestCase):
    def test_group_occupies_all_four_workers(self):
        self.assertEqual(lower_bound([0, 12], [0], [(0, 1, 6)] * 8), 12)
        self.assertEqual(lower_bound([0, 12], [0], [(0, 1, 6)] * 3), 6)

    def test_late_release_and_subsequent_deadline_accumulate(self):
        self.assertEqual(lower_bound([0, 8, 20, 23], [3, 0, 1], [(0, 1, 7), (1, 2, 10)]), 18)

    def test_conservation_cannot_make_historical_timing_impossible(self):
        with self.assertRaisesRegex(ValueError, "historical clock"):
            lower_bound([0, 4], [0], [(0, 1, 6)])
        with self.assertRaisesRegex(ValueError, "invalid job window"):
            lower_bound([0, 4], [0], [(1, 0, 4)])

    def test_summed_service_in_a_nested_release_window(self):
        self.assertEqual(lower_bound([0, 5, 15], [2, 0], [(0, 1, 5)] + [(1, 2, 4)] * 8), 13)


if __name__ == "__main__":
    unittest.main()
