import sys
import unittest
from itertools import combinations, product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from l2_decode_entry.solver import BYTES, solve  # noqa: E402

A, B, C, D = ((0, 3), (0, 5), (0, 6), (25, 4))


class DecodeEntry(unittest.TestCase):
    def test_source_latest_increment_publication_or_prefix_and_first_unseen_cold(self):
        jobs = {"increment": [(0, 1, A), (2, 3, A)], "decode": [(5, 6, A), (7, 8, D), (9, 10, C)]}
        groups = [[(A, 8, 1)], [(D, 7, 2)], [(C, 10, 1)]]
        out = solve(jobs, groups, {A, D}, [0, 2])[2]
        self.assertEqual(out["chosen_at_P"], [D])
        self.assertEqual(out["chosen_from_increment"], [A])
        for q in ("optimistic", "feasible"):
            w = out[q]
            self.assertEqual(w["occupied_at_I"], 2)
            self.assertEqual(w["hit_claims"], [5, 7])
            self.assertEqual(w["materializations"]["P"]["CUDA0"], 1)
            self.assertEqual(w["materializations"]["increment"]["CPU"], 1)
            self.assertEqual(w["primary_SET_bytes_by_phase_tier"]["decode"]["CPU"], 2 * BYTES)
            self.assertEqual(w["RAM_to_staging_bytes"], 2 * BYTES)
            self.assertEqual(w["group_max_sum_us"], 14)
            self.assertEqual((w["final_slots"], w["hit_counts"]["increment"]["CPU"]), (0, 0))

    def test_repeat_overflow_preserves_initial_choice(self):
        # The valuable A seed is retained across the two B lookups. B cannot be reinserted.
        jobs = {"increment": [], "decode": [(0, 1, B), (2, 3, B), (4, 5, A)]}
        out = solve(jobs, [[(B, 1, 1)], [(B, 7, 1)], [(A, 9, 1)]], {A}, [1])[1]
        self.assertEqual(out["chosen"], [A])
        self.assertEqual(out["optimistic"]["hit_claims"], [2, 4])
        self.assertEqual((out["optimistic"]["fits"], out["optimistic"]["peak_slots"]), (False, 2))
        w = out["feasible"]
        self.assertEqual((w["hit_claims"], w["peak_slots"], w["group_max_sum_us"]), ([4], 1, 11))
        self.assertEqual(w["dropped_repeat_intervals"], 1)

    def test_retention_starts_only_at_publication_and_group_order_is_by_key(self):
        # A's service starts while the B seed still fills the only slot. It finishes after
        # the B claim releases that slot. Its next lookup can hit without exceeding one slot.
        jobs = {"increment": [], "decode": [(1, 5, A), (2, 6, B), (8, 9, A)]}
        groups = [[(B, 10, 1), (A, 1, 1)], [(A, 5, 1)]]
        out = solve(jobs, groups, {B}, [1])[1]
        self.assertEqual(out["feasible"]["hit_claims"], [2, 8])
        self.assertTrue(out["optimistic"]["fits"])
        self.assertEqual(out["feasible"]["group_max_sum_us"], 3)

    def test_exhaustive_first_decode_seed_choices(self):
        jobs = {"increment": [(0, 1, A)], "decode": [(3, 5, A), (4, 6, B), (7, 8, C), (9, 10, A)]}
        for r0, r1, r2 in product((0, 6), repeat=3):
            rs = {A: r0, B: r1, C: r2}
            groups = [[(B, r1, 4), (A, r0, 2)], [(C, r2, 1)], [(A, 8, 2)]]
            results = solve(jobs, groups, {B, C}, range(4))
            for k, result in results.items():
                options = []
                for n in range(k + 1):
                    for choice in combinations((A, B, C), n):
                        joint = max(
                            2 + (0 if A in choice else rs[A]), 4 + (0 if B in choice else rs[B])
                        )
                        total = joint + 1 + (0 if C in choice else rs[C]) + 2
                        options.append((total, n, choice))
                best, _, chosen = min(options)
                self.assertEqual(result["optimistic"]["group_max_sum_us"], best)
                self.assertEqual(result["chosen"], list(chosen))

    def test_arbitrary_prefix_grants_unseen_first_key_and_charges_it(self):
        jobs = {"increment": [], "decode": [(1, 2, D)]}
        answer = solve(jobs, [[(D, 8, 1)]], None, [1])[1]
        self.assertEqual(answer["chosen_at_P"], [D])
        self.assertEqual(
            answer["feasible"]["materialized_bytes_by_origin_tier"]["P"]["CUDA0"], BYTES
        )
        self.assertEqual(answer["feasible"]["hit_claims"], [1])
        self.assertEqual(solve(jobs, [[(D, 8, 1)]], set(), [1])[1]["chosen"], [])

    def test_bad_journal_or_group_coverage_fails_closed(self):
        jobs = {"increment": [], "decode": [(0, 2, A), (1, 3, B)]}
        for groups in ([[(A, 2, 1)], [(B, 2, 1)]], [[(A, 2, 1)]], [[(A, 2, 1), (A, 2, 1)]]):
            with self.assertRaises(ValueError):
                solve(jobs, groups, set(), [1])
        for faulty in (
            {"increment": [(0, 3, A)], "decode": [(1, 2, B)]},
            {"increment": [], "decode": [(0, 2, A), (1, 4, A)]},
            {"increment": [], "decode": [(0, 2, A), (2, 4, B)]},
        ):
            with self.assertRaises(ValueError):
                solve(faulty, [], set(), [1])


if __name__ == "__main__":
    unittest.main()
