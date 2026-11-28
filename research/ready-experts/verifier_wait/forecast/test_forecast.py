"""Regression checks for causality, chargeable misses and timing at the decode boundary."""

import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
P = run_path(HERE / "price.py")
F = P["F"]


class ForecastTests(unittest.TestCase):
    def test_pruned_final_rank_belongs_to_last_token(self):
        rows = [SimpleNamespace(kind=3, b=87, a=2)]
        for layer in range(36):
            for ordinal in range(1 if layer == 35 else 2):
                rows.append(SimpleNamespace(kind=27, b=ordinal, layer=layer, a=0x04030201))
        rows.append(SimpleNamespace(kind=4))
        first, last = F["positions"](rows)
        self.assertEqual((first[0], last[0]), (87, 88))
        self.assertNotIn(35, first[1])
        self.assertEqual(last[1][35], (1, 2, 3, 4))

    def test_unseen_id_abstains_then_learns_on_return(self):
        model = F["Frequencies"]()
        self.assertEqual(model.token_scores(52, 0), ({}, 0))
        model.observe(52, {0: [1, 2, 3, 4]})
        selected = F["choices"](*model.token_scores(52, 0), {1, 2}, model.marginal[0])
        self.assertEqual(selected, ({3, 4},) * 4)
        self.assertEqual(model.token_scores(53, 0), ({}, 0))

    def test_unseen_upstream_antecedents_count_in_the_denominator(self):
        model = F["Frequencies"]()
        model.observe(7, {0: (1, 2, 3, 4), 2: (8, 9, 10, 11)})
        scores = model.upstream_scores((1, 20, 21, 22), 2)
        rule, control, top, _ = F["choices"](*scores, set(), model.marginal[2])
        self.assertEqual((rule, control, top), (set(), set(), {8, 9, 10, 11}))

    def test_tie_and_equal_issue_ablation(self):
        rule, control, _, _ = F["choices"](
            {1: 5, 2: 5, 3: 5, 4: 5, 5: 5}, 10, set(), {i: i for i in range(1, 6)}
        )
        self.assertEqual(rule, {1, 2, 3, 4})
        self.assertEqual(control, {2, 3, 4, 5})

    def test_correct_prediction_still_pays_copies_and_ignores_bank_indices(self):
        jobs = [(3, 700, 10, True), (9, 800, 20, False), (11, 500, 30, False)]
        self.assertEqual(P["remaining"](jobs, 3, 8_000_000_000), (30, 2))
        with self.assertRaises((AssertionError, ValueError, RuntimeError)):
            P["remaining"](jobs, 4, 8_000_000_000)

    def test_wrong_read_is_a_device_constraint_only_once(self):
        hot = [{"hot_ns": [20, 20]}]
        f = dict(W=3, repeat=1, all_hot_first_range_ns=[30, 40], all_hot_decode_ns=20)
        rows = [dict(residual_ns=90, device_bytes=130)]
        p = P["projected"](rows, f, hot, 1_000_000_000)
        self.assertEqual((p["first_ns"], p["decode_ns"]), ([140, 150], 130))

    def test_44_step_first_cut_excludes_the_tail(self):
        hots = [{"hot_ns": [1, 1]} for _ in range(46)]
        rows = [dict(residual_ns=0, device_bytes=0) for _ in hots]
        rows[44]["residual_ns"] = 100
        f = dict(W=3, repeat=1, all_hot_first_range_ns=[44, 48], all_hot_decode_ns=46)
        p = P["projected"](rows, f, hots, 1_000_000_000)
        self.assertEqual((p["first_ns"], p["decode_ns"]), ([44, 48], 146))


if __name__ == "__main__":
    unittest.main()
