import unittest
from collections import Counter
from pathlib import Path
from runpy import run_path

S = run_path(str(Path(__file__).with_name("score.py")))


class PredictionTest(unittest.TestCase):
    def test_condition_and_frequency_ablation(self):
        src = [(1, 2, 3, 4), (1, 5, 6, 7)]
        pairs = {(1, 1): {12: 2}, (1, 3): {11: 3, 99: 100}}
        freq = {1: {10: 9, 11: 1, 12: 1}}
        ranked = S["choose"](src, 1, pairs, freq, set(range(10, 16)))
        self.assertEqual(ranked["adjacent"], [12, 11, 10, 13])
        self.assertEqual(ranked["frequency"], [10, 11, 12, 13])

    def test_empty_evidence_and_small_eligible_set(self):
        self.assertEqual(
            S["choose"]([], 2, {}, {}, {3, 1}), {"adjacent": [1, 3], "frequency": [1, 3]}
        )

    def test_label_partition_and_duplicate_rejection(self):
        self.assertEqual(
            S["classify"]([3, 4, 5], {3, 6}, {3, 4, 6}),
            Counter(offers=3, strict=1, other_routed=1, unused=1),
        )
        with self.assertRaises(ValueError):
            S["classify"]([3, 3], {3}, {3})


if __name__ == "__main__":
    unittest.main()
