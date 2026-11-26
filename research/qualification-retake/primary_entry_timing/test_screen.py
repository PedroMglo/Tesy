import unittest

from screen import EXPERT, check_solution, donors, origin


class TestEntry(unittest.TestCase):
    def test_donor_accounts_both_empty_and_unused(self):
        rows = donors([{0, 1, 2}, set(range(40))], [{0, 5}, set(range(10, 43))])
        self.assertEqual(rows[0], dict(layer=0, empty=37, unused_residents=[1, 2], cap=39))
        self.assertEqual(rows[1]["cap"], 10)
        self.assertEqual(rows[1]["empty"], 0)

    def test_sources_do_not_double_charge(self):
        k = (4, 10)
        self.assertEqual(origin(k, {k}, {k}, {k}), "increment_publication")
        self.assertEqual(origin(k, set(), {k}, {k}), "resident_P")
        self.assertEqual(origin(k, set(), set(), {k}), "prefix_routed_only")
        self.assertEqual(origin(k, set(), set(), set()), "unproven")

    def test_replay_witness_and_reject_wrong_capacity_or_service(self):
        keys = {(0, 2), (0, 3), (25, 4)}
        origins = dict.fromkeys(keys, "resident_P")
        groups = [(0, {2: 4_000_000, 3: 3_000_000}), (25, {4: 2_500_000})]
        s = dict(
            reaches=True,
            k=1,
            chosen=[(25, 4)],
            remaining_us=4_000_000,
            k_minus_one_remaining_us=6_500_000,
            maximum_gain_us=2_500_000,
        )
        caps = [1] * 36
        out = check_solution(s, groups, caps, keys, origins, 0, 1, 1)
        self.assertEqual(out["capacity_bytes"], EXPERT)
        self.assertEqual(out["by_tier"]["CUDA"]["bytes_to_deliver_if_materialized"], EXPERT)
        for variant, budgets in (
            (dict(s, remaining_us=3_999_999), caps),
            (s, [0] * 36),
            (dict(s, k_minus_one_remaining_us=4_000_001), caps),
        ):
            with self.subTest(variant=variant, budgets=budgets), self.assertRaises(ValueError):
                check_solution(variant, groups, budgets, keys, origins, 0, 1, 1)
