"""Synthetic barriers for the C304 reload screen. No capture required."""

import unittest

from evaluate import EXPERT_BYTES, evaluate_choices, keyset, scales


class TestEvaluation(unittest.TestCase):
    def test_zero_choices_when_budget_already_fits(self):
        value = evaluate_choices([(0, {4: 17, 5: 9}), (25, {6: 7})], set(), 0)
        self.assertTrue(value["scales"]["1"]["reaches"])
        self.assertEqual(value["barrier_gain_us"], 0)
        self.assertEqual(value["oracle_same_layer_counts"]["remaining_us"], 24)
        self.assertEqual(value["capacity_bytes"], 0)

    def test_oracle_exploits_full_budget_even_if_k_zero_already_fits(self):
        groups = [(2, {1: 100, 2: 91}), (2, {3: 90}), (27, {4: 5})]
        selected = {(2, 1), (2, 65), (27, 4)}
        out = evaluate_choices(groups, selected, 0)
        self.assertEqual(out["read_floor_us"], 181)
        self.assertEqual(out["tiers"]["CPU"]["unused_choices"], 1)
        # Best use of two layer2 choices removes the entire 100/91 barrier.
        self.assertEqual(out["oracle_same_layer_counts"]["remaining_us"], 90)
        self.assertEqual(out["capacity_bytes"], 3 * EXPERT_BYTES)

    def test_oracle_cannot_spend_cuda_capacity_on_cpu(self):
        groups = [(1, {1: 99}), (27, {9: 5})]
        r = evaluate_choices(groups, {(27, 6)}, 5_333_333)
        self.assertEqual(r["barrier_gain_us"], 0)
        self.assertEqual(r["oracle_same_layer_counts"]["remaining_us"], 99)
        self.assertFalse(r["scales"]["1"]["reaches"])

    def test_tied_last_changes_only_if_both_selected(self):
        groups = [(8, {4: 19, 5: 19, 9: 7})]
        for picks, expected in (({(8, 4)}, 0), ({(8, 4), (8, 5)}, 12)):
            r = evaluate_choices(groups, picks, 0)
            self.assertEqual(r["barrier_gain_us"], expected)
        with self.assertRaisesRegex(ValueError, "disjoint"):
            evaluate_choices([(8, {4: 1}), (8, {4: 1})], set(), 0)

    def test_exact_three_way_gate_and_invalid_keys(self):
        self.assertTrue(scales(5_000_000, 333_333)["1"]["reaches"])
        self.assertFalse(scales(5_000_001, 333_333)["1"]["reaches"])
        self.assertTrue(scales(5_000_001, 333_333)["0.8"]["reaches"])
        for rows in ([[4, 1], [4, 1]], [[36, 42]], [[True, 4]]):
            with self.assertRaises(ValueError):
                keyset(rows)


if __name__ == "__main__":
    unittest.main()
