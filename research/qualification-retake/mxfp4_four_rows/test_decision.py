import unittest

from decision import ORDER, evaluate


def example(r=100, a=100, c=90, b=88):
    durations = {k: n for k, n in zip("RACB", (r, a, c, b), strict=True)}
    return [
        dict(
            cpu=cpu, regime=regime, arm=i, variant=v, rows=n, repeats=reps, duration_ns=durations[v]
        )
        for cpu in (0, 4)
        for regime, n, reps in (("hot", 64, 4096), ("stream", 23040, 12))
        for i, v in enumerate(ORDER, 1)
    ]


class FourRowDecision(unittest.TestCase):
    def test_inclusive_two_percent_and_ten_percent(self):
        result = evaluate(example(1000, 1000, 900, 882))
        self.assertTrue(result["sharing_at_least_2pct_all_pairs"])
        self.assertTrue(result["separate_C_MMID_gate"])
        self.assertEqual(result["decision"], "GO_ROUTED_MMID_B_FIXTURE")

    def test_parity_of_gain_is_not_sharing(self):
        result = evaluate(example(100, 100, 90, 90))
        self.assertTrue(result["shared_B_MMID_gate"])
        self.assertFalse(result["sharing_at_least_2pct_all_pairs"])

    def test_only_separate_meets_gate(self):
        result = evaluate(example(100, 100, 88, 91))
        self.assertEqual(result["decision"], "GO_ROUTED_MMID_C_FIXTURE")

    def test_second_pair_uses_own_r_and_a(self):
        for i in (-1, -2):
            rows = example()
            rows[i]["duration_ns"] = 96
            self.assertEqual(evaluate(rows)["decision"], "NO_GO_FOUR_ROWS")

    def test_one_missing_reordered_or_invalid_arm(self):
        base = example()
        for rows in (
            base[:-1],
            [base[1], base[0], *base[2:]],
            [base[0] | {"duration_ns": False}, *base[1:]],
            [base[0] | {"rows": 65}, *base[1:]],
        ):
            with self.assertRaises(ValueError):
                evaluate(rows)
