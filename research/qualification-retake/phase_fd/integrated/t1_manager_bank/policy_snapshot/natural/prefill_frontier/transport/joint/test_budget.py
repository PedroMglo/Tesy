import unittest
from pathlib import Path
from runpy import run_path

budget = run_path(Path(__file__).with_name("budget.py"))


class WorkBudgetTests(unittest.TestCase):
    def test_service_at_limit_and_missing_time(self):
        at = budget["price"](1000, 20, 8, 4, 32)
        self.assertEqual((at["margin_ns"], at["decision"]), (0, "HEADROOM_ONLY"))
        self.assertEqual(at["payload_budget_at_this_mean_rate_bytes"], 1000)
        over = budget["price"](1000, 20, 8, 4, 31)
        self.assertEqual((over["margin_ns"], over["decision"]), (-1, "NO_GO_FIXED_PRICES"))
        self.assertEqual(over["payload_budget_at_this_mean_rate_bytes"], 950)

    def test_cross_order_mixture_and_empty_gap(self):
        frontier = dict(
            budget_prefill_plus_decode_ns=31,
            gaps={"total_ns": 5, "protected_ns": 2},
            work={"prefill": {"payload_bytes": 100}},
            pack_orders={"PR": {"conditional_decode_ns": 10}, "RP": {"conditional_decode_ns": 12}},
        )
        result = budget["cross"](frontier, {"PR": 17, "RP": 19})
        self.assertEqual(result["all_gaps_free"]["decision"], "HEADROOM_ONLY")
        self.assertEqual(result["ideal_two_tiles"]["decision"], "INCONCLUSIVE_ORDERS")
        self.assertEqual(result["serial"]["decision"], "NO_GO_FIXED_PRICES")
        self.assertEqual(len(result["serial"]["pairs"]), 4)


if __name__ == "__main__":
    unittest.main()
