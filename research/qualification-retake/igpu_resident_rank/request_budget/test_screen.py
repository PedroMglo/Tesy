import unittest
from decimal import Decimal
from pathlib import Path
from runpy import run_path

S = run_path(Path(__file__).with_name("screen.py"))


class BudgetTests(unittest.TestCase):
    def test_all_used_or_overdrawn(self):
        score = S["boundary"](12_000_000_000, 3_000_000_000, 2, 4_000_000_000, 2_000_000_000)
        self.assertEqual(score["critical_fraction_of_lower_bytes"], 0.5)
        self.assertEqual(score["max_average_ns_per_step"], 500_000_000)
        over = S["boundary"](12_000_000_000, 1_000_000_000, 2, 0, 2_000_000_000)
        self.assertLess(over["remaining_ns"], 0)
        self.assertIsNone(over["critical_fraction_of_lower_bytes"])

    def test_counter_and_collection_order(self):
        def row(t, v):
            return dict(
                elapsed_s=Decimal(t),
                collection_s=Decimal("0.08"),
                pid=1,
                process_identity={"pid": 1},
                proc=dict(read_bytes=v, rchar=v, syscr=v),
            )

        good = [row("1", 4), row("2", 7)]
        samples = S["samples"](good, {"pid": 1}, 0)
        bounds = S["CLOCK"]["extrema"](
            samples, S["CLOCK"]["between"](1_100_000_000, 1_700_000_000), 5
        )
        self.assertEqual(bounds["definitely_inside_samples"], [0, 0])
        with self.assertRaises(ValueError):
            S["samples"]([*good, row("3", 1)], {"pid": 1}, 0)
        with self.assertRaises(ValueError):
            S["samples"]([row("1", 3), row("1.01", 4)], {"pid": 1}, 0)


if __name__ == "__main__":
    unittest.main()
