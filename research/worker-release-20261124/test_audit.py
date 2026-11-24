"""Model-free checks on the projection and historical arithmetic."""

import unittest

from audit import merge
from cost import report


class PrefixProjection(unittest.TestCase):
    def test_enumerates_both_cross_journal_orders(self):
        viable = merge([0, 1, 0], [0, 1, 0], [])
        self.assertEqual(viable, [{0, 1, 2}, {0, 1, 2}, {0, 1, 2}])

    def test_constraints_and_capacity_narrow_the_occupancy(self):
        viable = merge([0, 3, 0], [0, 2, 0], [(1, 1, True)])
        self.assertEqual(viable, [{0}, {0}, {0, 1, 2}])

    def test_never_credits_a_prefix_with_no_full_reconstruction(self):
        # Either P1 or S1 can start. Starting at P1 would deadlock until S1,
        # but together they would exceed four. Only the staging-first path works.
        viable = merge([0, 3, 0], [0, 2, 0], [(2, 1, False)])
        self.assertEqual(viable, [{0, 1, 2}, {2}, {2}])

    def test_inconsistent_cross_edges_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "no interleaving"):
            merge([0, 1, 0], [0, 1, 0], [(1, 1, True), (1, 1, False)])

    def test_cost_receipts_preserve_the_historical_negative(self):
        cases = report()["cases"]
        for case, threshold in (("nominal153", 17.616369), ("code153", 18.021172)):
            row = cases[case]
            self.assertAlmostEqual(row["global_infima_pct_with_other_case_fixed"]["decode_route"],
                                   threshold, places=6)
            self.assertEqual(len(row["trace_off_arms_ABBA"]), 4)
            self.assertTrue(row["historical_gate_checks"]["other_case_protected"])
            self.assertFalse(row["historical_gate_checks"]["global_decode"])


if __name__ == "__main__":
    unittest.main()
