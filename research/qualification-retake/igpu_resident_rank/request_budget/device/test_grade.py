import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grade


def sample(milliseconds, counter=None, sectors=None):
    n = milliseconds if counter is None else counter
    return grade.Sample(
        milliseconds * 10**6,
        milliseconds * 10**6 + 10,
        n,
        n,
        milliseconds if sectors is None else sectors,
        0,
    )


class Deltas(unittest.TestCase):
    def test_different_metrics_enclosures_and_density(self):
        rows = [sample(x, x * 5) for x in (10, 100, 200, 300, 400, 460, 530)]
        result = grade.interval(rows, 100_000_005, 460_000_006)
        self.assertEqual(result["inside_samples"], 3)
        self.assertEqual(result["cgroup_submitted_read_bytes"]["lower"], 1000)
        self.assertEqual(result["cgroup_submitted_read_bytes"]["upper"], 2600)
        self.assertEqual(result["namespace_completed_read_bytes"]["lower"], 200 * 512)
        self.assertEqual(result["density"], "SUFFICIENT")

    def test_missing_row_regression_gap_and_one_inner(self):
        def bounds(rows):
            return grade.interval(rows, 50 * 10**6, 750 * 10**6)

        missed = bounds([sample(1), sample(100), sample(250, -1), sample(450), sample(800)])
        self.assertIsNone(missed["cgroup_submitted_read_bytes"]["lower"])
        self.assertEqual(missed["namespace_completed_read_bytes"]["lower"], 350 * 512)
        regressed = bounds([sample(1), sample(100), sample(300, 30), sample(600), sample(800)])
        self.assertIsNone(regressed["cgroup_submitted_read_bytes"]["lower"])
        sparse = bounds([sample(1), sample(100), sample(710), sample(800)])
        self.assertEqual(sparse["density"], "INCONCLUSIVE")
        one = bounds([sample(1), sample(100), sample(800)])
        self.assertIsNone(one["cgroup_submitted_read_bytes"]["lower"])
        self.assertEqual(one["cgroup_submitted_read_bytes"]["upper"], 799)
        self.assertEqual(bounds([])["density"], "INCONCLUSIVE")

    def test_price_and_distinct_historical_metric(self):
        target = 10**10

        def fn(allowance, min_bytes, covered=True):
            return grade.price(target + 1000, 1000 + allowance, min_bytes, covered)[
                "classification"
            ]

        self.assertEqual(fn(0, 99), "NO_TIME_IN_FIXED_EXTERIOR_SCENARIO")
        self.assertEqual(fn(10, 81), "CONDITIONAL_EXCLUSION_ABOVE_CRITICAL_FRACTION")
        self.assertEqual(fn(10, 80), "NO_EXCLUSION_FROM_OBSERVED_MINIMUM")
        self.assertEqual(fn(10, 999, False), "INCONCLUSIVE_ACCOUNTING")
        h = grade.assess_history()
        self.assertEqual(h["rop"]["metric"], "PROCESS_READ_BYTES")
        self.assertEqual(h["por"]["clocks"]["sample"]["available_ns"], 205665433)

    def test_reject_malformed_trace(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "trace.tsv"
            path.write_text(grade.HEADER + "\n10\t20\t-1\t-1\t0\t1\n30\t40\t4\t1\t5\t0\n")
            self.assertEqual(len(grade.read_trace(path)), 2)
            with path.open("a") as f:
                f.write("35\t50\t9\t2\t8\t0\n")
            with self.assertRaises(ValueError):
                grade.read_trace(path)


if __name__ == "__main__":
    unittest.main()
