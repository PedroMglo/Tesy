"""Regression checks for the crossing block, transferred wait, and neutrality failure."""

import copy
import json
import unittest
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
GRADE = run_path(HERE / "grade.py")
COMBINED = json.loads(
    (HERE.parent / "draft20/joint/evidence-20261128-r01/combined.json").read_bytes()
)
WITNESS = json.loads((HERE / "evidence-20261128-r01/barriers.json").read_bytes())["evidence"]


class VerifierCuts(unittest.TestCase):
    def test_strictly_prior_and_crossing(self):
        result = GRADE["price"](WITNESS, COMBINED)
        for role in ("B0a", "B1", "B0b"):
            rows = [r for r in WITNESS[role]["decode"] if r["width"] == 3]
            before = [r for r in rows if r["at"] + r["keep"] - 1 < 44]
            crosses = [r for r in rows if r["at"] - 1 < 44 <= r["at"] + r["keep"] - 1]
            self.assertEqual(len(before), 9)
            self.assertEqual(len(crosses), 1)
            self.assertEqual(crosses[0]["at"], 43)
            sums = result["wall_by_scope_ns"][role]
            self.assertEqual(sums["before"], sum(r["wall_ns"] for r in before))
            self.assertEqual(sums["first"] - sums["before"], crosses[0]["wall_ns"])

    def test_neutrality_is_required(self):
        broken = copy.deepcopy(WITNESS)
        for r in broken["B0b"]["decode"]:
            r["wall_ns"] *= 2
        p = GRADE["price"](broken, COMBINED)
        self.assertFalse(p["observer_neutral"])
        self.assertEqual(p["decision"], "INCONCLUSIVE")

    def test_clock_rounding_is_capped(self):
        r = dict(wall_ns=7300, counts=[3, 0, 1, 13219200, 2, 1, 0, 6, 0])
        self.assertEqual(GRADE["cap_wait"](r), 7300)
        r["wall_ns"] = 14000
        self.assertEqual(GRADE["cap_wait"](r), 9000)

    def test_both_operational_cuts_on_same_row(self):
        p = GRADE["price"](WITNESS, COMBINED)
        verdicts = {
            r["first_ns"] <= 10**10 and r["decode_ns"] <= 47 * 10**9 // 6 for r in p["arms"]
        }
        self.assertEqual(verdicts, {True, False})
        self.assertTrue(p["observer_neutral"])
        self.assertEqual(p["decision"], "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
