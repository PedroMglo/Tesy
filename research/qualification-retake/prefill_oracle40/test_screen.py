import itertools
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

import screen
from test_cache_bound import brute  # reuse the exhaustive independent paging reference


def fixture(widths):
    rows = []
    for i, width in enumerate(widths):
        for layer in range(36 if i == len(widths) - 1 else 35):
            n = width if layer < 35 else 1
            for expert in range(min(n * 4, 20)):
                rows.append(
                    {
                        "kind": "DEMAND",
                        "layer": layer,
                        "n_tokens": n,
                        "expert": expert,
                        "wave": -1 if 4 * n <= 40 else expert // 18,
                    }
                )
    return rows


class PrefillOracle(unittest.TestCase):
    def test_small_ties_and_every_possible_initial_cache(self):
        cohorts = [(0,), (1,), (0, 2), (2, 3)]
        for sequence in itertools.product(cohorts, repeat=4):
            first, second = list(sequence[:1]), list(sequence[1:])
            for k in (2, 3):
                measured = screen.solve(first, second, k)
                self.assertEqual(measured["optimal_total"], brute(sequence, k))
                self.assertEqual(
                    measured["optimal_total"],
                    measured["optimal_call5"] + measured["optimal_call148"],
                )
                self.assertLessEqual(measured["distinct_floor"], measured["optimal_total"])

    def test_only_one_free_start(self):
        self.assertEqual(screen.solve([(0, 1)], [(2, 3)], 2)["optimal_total"], 2)
        self.assertEqual(screen.cache_bound.minimum([(2, 3)], 2), 0)

    def test_pass_includes_hits_and_output_pruning(self):
        rows = fixture([32, 20])
        groups = screen.demands_by_layer(rows, [32, 20])
        self.assertEqual(list(map(len, groups[0])), [18, 2, 18, 2])
        self.assertEqual(groups[-1], [(0, 1, 2, 3)])

    def test_reject_geometry_changes(self):
        for change, reason in (
            ("small_wave", "mode"),
            ("large_remap", "mode"),
            ("duplicate", "identity"),
            ("gap", "sequence"),
            ("lost_layer", "coverage"),
        ):
            with self.subTest(change=change):
                rows = fixture([32, 20])
                if change == "small_wave":
                    for row in rows[-4:]:
                        row["wave"] = 0
                elif change == "large_remap":
                    for row in rows[:20]:
                        row["wave"] = -1
                elif change == "duplicate":
                    rows[18]["expert"] = rows[0]["expert"]
                elif change == "gap":
                    rows[18]["wave"] = 2
                else:
                    rows = [r for r in rows if r["layer"] != 7]
                with self.assertRaisesRegex(ValueError, reason):
                    screen.demands_by_layer(rows, [32, 20])

    def test_threshold_and_missing_raw(self):
        budget = Fraction("2.427104435")
        self.assertIn("INCONCLUSIVE", screen.decision(826, budget)["comparison"])
        self.assertIn("NO_GO", screen.decision(827, budget)["comparison"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = screen.run(root / "missing.raw", root, root)
            self.assertEqual(result["status"], "NOT_RUN_RAW_REQUIRED")
