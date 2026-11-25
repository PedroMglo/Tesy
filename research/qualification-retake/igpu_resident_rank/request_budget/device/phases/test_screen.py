import sys
import unittest
from decimal import Decimal as D
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import screen


class PhaseBounds(unittest.TestCase):
    def test_envelope_nonzero_residual_both_phases(self):
        b, t = screen.envelope(D(10), D("13.1"), D(1000), D(2000))
        self.assertEqual(b["prompt"], (9999998000, 10100002000, 10999998000, 11100002000))
        self.assertEqual(
            b["decode"], (10999998000, 11100002000, 13099998000 - 100000000, 13100002000)
        )
        cls = screen.GRADE["Sample"]
        rows = [
            cls(i * 100000000 - 15, i * 100000000 + 15, i * 1024, i, i * 3, 0)
            for i in range(98, 133)
        ]
        p = screen.phase(rows, b["prompt"])
        self.assertEqual(p["inside_samples"], 8)
        self.assertEqual(p["counters"]["cgroup_submitted_rbytes"]["lower"], 7 * 1024)
        self.assertEqual(p["counters"]["cgroup_submitted_rbytes"]["upper"], 13 * 1024)
        self.assertEqual(p["counters"]["namespace_completed_read_bytes"]["lower"], 7 * 3 * 512)
        self.assertEqual(p["status"], "BOUNDED_NATIVE_PHASE")

    def test_inconclusive_on_missing_intersection_and_regression(self):
        cls = screen.GRADE["Sample"]
        rows = [
            cls(i, i + 1, 0 if i == 5000 else i, i, i, 0) for i in (1000, 3000, 5000, 7000, 9000)
        ]
        p = screen.phase(rows, (2000, 2500, 7500, 8000))
        self.assertEqual(p["status"], "INCONCLUSIVE_PHASE_OBSERVATION")
        self.assertIsNone(p["counters"]["cgroup_submitted_rbytes"]["lower"])
        self.assertEqual(p["counters"]["namespace_read_sectors"]["lower"], 4000)
        p = screen.phase(rows, (2000, 6000, 4000, 8000))
        self.assertEqual(p["inside_samples"], 0)
        with self.assertRaisesRegex(ValueError, "serial"):
            screen.envelope(D(1), D(2), D(1000), D(1000))


if __name__ == "__main__":
    unittest.main()
