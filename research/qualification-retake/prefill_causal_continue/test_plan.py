import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prefill_causal import plan as prior  # noqa: E402
from prefill_causal_continue import plan  # noqa: E402


class Continuation(unittest.TestCase):
    def setUp(self):
        self.start = [(1, 1, 0, 0, (0, 1, 2, 3)), (9, 1, 0, 1, (0, 1, 4, 5))]
        self.rows = self.start + [(10, 1, 0, 2, (2, 3, 4, 5)), (11, 1, 25, 3, (8, 9, 10, 11))]
        self.empty = [set() for _ in range(36)]
        self.target = [set() for _ in range(36)]
        self.target[25] = {9, 14}

    def test_no_repair_at_i_tier_counts_and_own_f_cost(self):
        for rule in prior.RULES:
            # The native I anchor omits 2/3/4/5. Artificially restoring it would lose hits.
            native_i = [set() for _ in range(36)]
            native_i[0] = {0, 1, 6, 7}
            ref = prior.simulate(self.start, rule, native_i)
            self.assertEqual(ref["restore_I_identity_floor"]["CPU"]["loads"], 2)
            sim = plan.history(self.rows, rule, ref, self.target)
            self.assertEqual(sim["phases"]["decode"]["CPU"]["hits"], 4)
            self.assertEqual(sim["phases"]["decode"]["CUDA0"]["misses"], 4)
            self.assertEqual(sim["restore_F_identity_floor"]["CUDA0"]["loads"], 1)
            self.assertEqual(
                plan.count_loads(sim),
                {"prefix": 4, "increment": 2, "decode": 4, "restored_total": 11},
            )

    def test_cuts_and_each_phase_must_match(self):
        ref = prior.simulate(self.start, "votes", self.empty)
        for field in ("P_membership_sha256", "I_membership_sha256", "hits", "logical_load_bytes"):
            bad = deepcopy(ref)
            if "sha256" in field:
                bad[field] = "changed"
            else:
                bad["phases"]["prefix"]["CPU"][field] += 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                plan.history(self.rows, "votes", bad, self.target)
        with self.assertRaises(ValueError):
            plan.history(self.start, "votes", ref, self.target)

    def test_future_decode_rows_have_no_effect_before_i(self):
        ref = prior.simulate(self.start, "lru", self.empty)
        a = plan.history(self.rows, "lru", ref, self.empty)
        altered = self.rows[:-1] + [(11, 1, 0, 3, (0, 1, 2, 3))]
        b = plan.history(altered, "lru", ref, self.empty)
        for cut in ("P", "I"):
            self.assertEqual(a[cut + "_membership_sha256"], b[cut + "_membership_sha256"])
        self.assertNotEqual(a["F_membership_sha256"], b["F_membership_sha256"])

    def test_votes_and_recency_survive_i(self):
        # Fill all forty; earlier rank votes keep 0..3 hot although last touched >35 entries ago.
        prefix = [(1, 1, 0, i, (0, 1, 2, 3)) for i in range(4)]
        prefix.extend((8, 1, 0, i, tuple(range(i, i + 4))) for i in range(4, 40, 4))
        prefix.append((9, 1, 0, 40, (36, 37, 38, 39)))
        suffix = [(10, 1, 0, 41, (40, 41, 42, 43)), (11, 1, 0, 42, (0, 1, 2, 3))]
        for rule, expected_misses in (("votes", 4), ("lru", 8)):
            ref = prior.simulate(prefix, rule, self.empty)
            sim = plan.history(prefix + suffix, rule, ref, self.empty)
            self.assertEqual(sim["phases"]["decode"]["CPU"]["misses"], expected_misses)

    def test_combined_threshold_and_all_individual_guards(self):
        control = dict(prefix=53, increment=50, decode=200, restored_total=303)
        candidate = dict(prefix=50, increment=50, decode=175, restored_total=303)
        self.assertTrue(plan.compare(candidate, control)["pass"])
        for change in (
            {"prefix": 54},
            {"increment": 51, "decode": 160},
            {"decode": 176},
            {"decode": 201, "increment": 20},
            {"restored_total": 304},
        ):
            self.assertFalse(plan.compare(dict(candidate, **change), control)["pass"])


if __name__ == "__main__":
    unittest.main()
