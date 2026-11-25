import unittest
from pathlib import Path
from runpy import run_path

S = run_path(str(Path(__file__).with_name("screen.py")))


class Threshold(unittest.TestCase):
    def test_plateau_and_domain(self):
        self.assertEqual(S["threshold"](lambda r: r // 2 >= 2, 1, 12), (3, 4))
        self.assertEqual(S["threshold"](lambda r: True, 1, 12), (None, 1))
        self.assertEqual(S["threshold"](lambda r: False, 1, 12), (12, None))

    def test_joint_is_later_clock(self):
        out = S["certificate"](lambda b: (b - 10_000_000, b - 44_000_001))["thresholds"]
        self.assertEqual(out["first"][1]["payload_Bps"], 10_000_000)
        self.assertEqual([x["payload_Bps"] for x in out["joint"]], [44_000_000, 45_000_000])

    def test_worker_time_and_global_active_time(self):
        occ = S["occupancy"]({0: [(2, 5), (10, 12)], 1: [(4, 6)], 2: [(4, 5)]})
        self.assertEqual(occ, {0: 4, 1: 5, 2: 0, 3: 1, 4: 0})
        with self.assertRaises(ValueError):
            S["occupancy"]({0: [(0, 5), (4, 12)]})


if __name__ == "__main__":
    unittest.main()
