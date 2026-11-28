"""Check the paired reader's acceptance and failure boundaries before taking transfer times."""

import unittest
from pathlib import Path
from runpy import run_path

parse = run_path(Path(__file__).resolve().with_name("grade.py"))["parse"]


class ReaderReceipts(unittest.TestCase):
    def setUp(self):
        self.plan = dict(pack_stat=[1, 2, 3, 4, 5], unique=2, counts=[[1] * 46, [2] * 46])
        self.lines = ["fd 1 2 3 4 5", "parity 2 100"]
        for arm, mode in enumerate((0, 1, 1, 0), 1):
            for step in range(1, 47):
                self.lines.append(f"step {arm} {mode} {step} {mode+1} 1 10 11")
        self.lines.append("drained")

    def test_paired_arms_keep_both_clock_scopes(self):
        raw = parse(self.lines, self.plan)
        self.assertEqual([a["mode"] for a in raw["arms"]], list("DHHD"))
        self.assertEqual(raw["arms"][0]["steps"][43], [1, 1, 10, 11])
        self.assertEqual(raw["checked_timed_markers"], 9 * 46 * 6)

    def test_missing_drain_and_clock_inversion_stop(self):
        with self.assertRaises(ValueError):
            parse(self.lines[:-1], self.plan)
        self.lines[2] = "step 1 0 1 1 1 11 10"
        with self.assertRaises(ValueError):
            parse(self.lines, self.plan)


if __name__ == "__main__":
    unittest.main()
