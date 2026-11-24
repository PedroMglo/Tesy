"""Model-free checks on the projection and historical arithmetic."""

import unittest
from itertools import combinations

from audit import locked_attach_edge, merge
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

    def test_mutex_orders_other_producer_on_each_side_of_accept(self):
        # P2 assigns the blocked demand (a second primary worker). S1 starts its
        # producer. The other producer's S2/S4 start/end may flank the attach.
        primary = [0, 1, 2, 1, 0]
        for stage, attach, expected in [
            ([0, 1, 2, 2, 1, 0], 3, 4),  # other producer starts before attach
            ([0, 1, 1, 2, 1, 0], 2, 3),  # other producer starts after attach
            ([0, 1, 2, 1, 1, 0], 4, 3),  # other producer finishes before attach
        ]:
            with self.subTest(stage=stage, attach=attach):
                accept = 2
                edges = [(accept, 1, False), (accept, attach, True),
                         (accept + 1, attach, False)]
                if attach == 3:
                    relaxed = merge(primary, stage, edges)
                    self.assertEqual({primary[accept] + stage[s]
                                      for s in relaxed[accept] if s < attach}, {3, 4})
                viable = merge(primary, stage, edges + [locked_attach_edge(accept, attach)])
                self.assertEqual({s for s in viable[accept] if s < attach}, {attach - 1})
                self.assertEqual(primary[accept] + stage[attach - 1], expected)

                # Independent enumeration of complete orders. An intervening
                # unlocked primary record would be allowed in a real trace.
                n, m = len(primary) - 1, len(stage) - 1
                observed = [set() for _ in primary]
                for positions in combinations(range(n + m), n):
                    p_positions = set(positions)
                    p = s = 0
                    path = [(0, 0)]
                    for i in range(n + m):
                        if i in p_positions:
                            p += 1
                            if (p == accept and s != attach - 1
                                    or p == accept + 1 and s < attach):
                                break
                        else:
                            s += 1
                            if s == attach and p < accept:
                                break
                        if primary[p] + stage[s] > 4:
                            break
                        path.append((p, s))
                    else:
                        for p, s in path:
                            observed[p].add(s)
                self.assertEqual(viable, observed)

    def test_audit_rejects_an_intervening_staging_writer(self):
        # Force primary accept before the previous staging event. Both
        # journals fit capacity in isolation and the historic relaxation.
        before_attach = [(1, 2, True), (1, 1, True)]
        merge([0, 1, 0], [0, 1, 1, 0], before_attach)
        with self.assertRaisesRegex(ValueError, "no interleaving"):
            merge([0, 1, 0], [0, 1, 1, 0], before_attach + [locked_attach_edge(1, 2)])

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
