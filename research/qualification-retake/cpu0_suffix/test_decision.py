import unittest

from decision import ORDER, evaluate


def family(suffixes=(100, 100, 100, 100)):
    values = iter(suffixes)
    return [dict(run_index=i, observer=mode, graph_ns=1000,
                 suffix_ns=next(values) if mode == "ON" else None)
            for i, mode in enumerate(ORDER)]


class TestEvaluation(unittest.TestCase):
    def test_disjoint_chronological_pairs_and_off_uncertainty(self):
        rows = family((99, 100, 101, 110))
        pairs = evaluate(rows)["pairs"]
        self.assertEqual([(p["off_index"], p["on_index"]) for p in pairs],
                         [(0, 1), (3, 2), (5, 4), (6, 7)])
        self.assertEqual(evaluate(rows)["on_suffix_ns"]["median"], 100.5)
        for p in pairs:
            self.assertEqual(p["off_suffix_identified_interval_ns"], [0, 1000])
            # Two compatible allocations of the unmarked OFF clock yield opposite effects.
            s = p["on_suffix_ns"]
            self.assertLess(10, s)
            self.assertLess(s, 990)
            self.assertEqual(10 + 990, 990 + 10)
        self.assertIsNone(evaluate(rows)["off_suffix_point_estimate_ns"])
        self.assertIsNone(evaluate(rows)["c135_nonoverlapped_compute_floor_ns"])

    def test_inclusive_exact_limits(self):
        rows = family((85, 100, 100, 115))
        rows[1]["graph_ns"] = 850
        rows[7]["graph_ns"] = 1150
        self.assertEqual(evaluate(rows)["status"], "REPRODUCED_ON_SUFFIX_IN_CPU0_FIXTURE")
        rows[1]["graph_ns"] -= 1
        self.assertFalse(evaluate(rows)["paired_graphs_within_band"])
        self.assertEqual(evaluate(rows)["status"], "INCONCLUSIVE_OBSERVER_OR_DISPERSION")
        rows[1]["graph_ns"] += 1
        rows[7]["suffix_ns"] += 1
        self.assertFalse(evaluate(rows)["on_suffixes_within_band"])
        self.assertTrue(evaluate(rows)["paired_graphs_within_band"])
        self.assertEqual(evaluate(rows)["status"], "INCONCLUSIVE_OBSERVER_OR_DISPERSION")

    def test_schema_and_censoring(self):
        for i, name, bad in [(0, "suffix_ns", 0), (1, "suffix_ns", None),
                             (2, "observer", "OFF"), (2, "suffix_ns", 1001),
                             (4, "run_index", True), (5, "graph_ns", False),
                             (0, "graph_ns", 4.2), (7, "suffix_ns", -1)]:
            with self.subTest(i=i, name=name, bad=bad):
                rows = family()
                rows[i][name] = bad
                with self.assertRaises(ValueError):
                    evaluate(rows)
        with self.assertRaises(ValueError):
            evaluate(family()[:-1])
