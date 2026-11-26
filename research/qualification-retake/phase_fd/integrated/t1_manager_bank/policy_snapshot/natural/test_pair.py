import unittest
from pathlib import Path
from runpy import run_path

account = run_path(str(Path(__file__).with_name("pair.py")))


class PairAccounting(unittest.TestCase):
    def test_missing_power_retains_only_measured_intervals(self):
        rows = [
            dict(elapsed_s=t, pid=8, gpu=dict(uuid="same", power_w=p))
            for t, p in ((1, 5), (3, 15), (4, None), (7, 8))
        ]
        result = account["energy"](rows, 8)
        self.assertEqual((result["estimated_gpu_j"], result["covered_s"]), (20, 2))
        self.assertEqual(result["missing_power_samples"], 1)
        with self.assertRaises(ValueError):
            account["energy"](rows + [rows[0]], 8)

    def test_product_count_includes_the_first_id(self):
        row = dict(prefill_s=10, decode_s=9, first_final_s=19)
        budgets = account["phase_budget"](row)
        self.assertEqual(budgets, {47: 2166666667, 46: 2333333334})


if __name__ == "__main__":
    unittest.main()
