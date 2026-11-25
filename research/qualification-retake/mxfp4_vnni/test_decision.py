import unittest

from decision import evaluate


def example():
    return [
        dict(
            cpu=cpu, regime=kind, arm=i, variant=variant, rows=rows, repeats=repeats, duration_ns=n
        )
        for cpu in (0, 4)
        for kind, rows, repeats in (("hot", 64, 4096), ("stream", 23040, 12))
        for i, (variant, n) in enumerate(
            zip("RABBAR", (100, 100, 90, 90, 100, 100), strict=True), 1
        )
    ]


class DecisionTest(unittest.TestCase):
    def test_threshold_inclusive_and_second_R_denominator(self):
        rows = example()
        self.assertEqual(evaluate(rows)["decision"], "GO_ROUTED_MMID_FIXTURE")
        rows[-1]["duration_ns"] = 99
        self.assertEqual(evaluate(rows)["decision"], "NO_GO_GLOBAL_KERNEL_PROMOTION")

    def test_work_and_order(self):
        rows = example()
        rows[9]["repeats"] = 11
        with self.assertRaises(ValueError):
            evaluate(rows)
