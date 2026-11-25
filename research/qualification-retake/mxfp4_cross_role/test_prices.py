import unittest
from pathlib import Path
from runpy import run_path

m = run_path(Path(__file__).with_name("prices.py"))


class TransportPrices(unittest.TestCase):
    def test_set_prices_stay_attached_to_each_job_on_crossover(self):
        # At q=1 the first worker is critical. At q=0.5 the second becomes critical.
        chains = [[(100, 0), (20, 60)], [(0, 80)]]
        fixed = m["OUTSIDE"]
        self.assertEqual(m["decode_scaled"](chains, 1, 1), fixed + 180)
        self.assertEqual(m["decode_scaled"](chains, 1, 2), fixed * 2 + 300)
        self.assertEqual(m["decode_scaled"](chains, 0, 1), fixed + 140)

    def test_integer_threshold_respects_both_constraints(self):
        chains = [[(10**10, 0)]]
        p = 10**9
        q = m["cutoff"](chains, p, 0)
        ppm = m["PPM"]
        self.assertTrue(0 < q < ppm)
        self.assertGreaterEqual(min(m["margins"](chains, p, 0, q, ppm)[:2]), 0)
        self.assertLess(min(m["margins"](chains, p, 0, q + 1, ppm)[:2]), 0)
        self.assertIsNone(m["cutoff"]([[(0, 10**10)]], p, 0))

    def test_coverage_counts_only_disk_and_layer_specific_identity(self):
        def jobs(*sources):
            return [dict(expert=2, source=s) for s in sources]

        g = [dict(layer=0, jobs=jobs("disk", "bank", "disk")), dict(layer=25, jobs=jobs("disk"))]
        row = m["coverage"](g, {(0, 2)}, 3)
        self.assertEqual(row["both"]["all_distinct_keys"], 2)
        self.assertEqual(row["CPU"]["sample_job_occurrences"], 2)
        self.assertEqual(row["CUDA"]["sample_distinct_keys"], 0)


if __name__ == "__main__":
    unittest.main()
