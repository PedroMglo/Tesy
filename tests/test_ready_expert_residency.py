import json
import unittest
from pathlib import Path
from runpy import run_path

M = run_path(str(Path(__file__).resolve().parents[1] / "research/ready-experts/residency.py"))
Call = M["BASE"]["Call"]
Job = M["Job"]


class ResidentWeights(unittest.TestCase):
    def test_public_receipts_reconcile_without_private_journals(self):
        folder = M["HERE"]
        overlap = json.loads((folder / "overlap-result.json").read_text())
        residency = json.loads((folder / "residency-result.json").read_text())
        selection = json.loads((folder / "selection-result.json").read_text())
        existence = json.loads((folder / "existence-result.json").read_text())
        for label, arm in overlap["arms"].items():
            charged = sum(s["charged"] for s in arm["phases"].values())
            self.assertEqual(charged + arm["free_jobs"], arm["jobs"])
            cases = list(residency["arms"][label]["cases"].values())
            cases.extend(selection["arms"][label].values())
            cases.append(existence["arms"][label]["witness"])
            for row in cases:
                phases = row["phases"]
                before = phases["decode_before_final"]["floor_ns"]
                self.assertEqual(
                    row["first_final"],
                    arm["outside_calls_ns"]["first_final"] + phases["prefill"]["floor_ns"] + before,
                )
                self.assertEqual(
                    row["decode"],
                    arm["outside_calls_ns"]["decode"] + before + phases["decode_tail"]["floor_ns"],
                )
        for cap in residency["uniform_minima"].values():
            self.assertGreaterEqual(min(cap["margin_ns_at_min"].values()), 0)
            self.assertLess(min(cap["margin_ns_at_one_less"].values()), 0)
        common = min(min(a["witness"]["margin_ns"].values()) for a in existence["arms"].values())
        self.assertEqual(common, existence["common_joint_margin_ns"])
        self.assertGreater(common, 0)

    def test_credit_goes_to_the_critical_job_only(self):
        calls = [Call(1, 16, 13, 0, 3, 3)]
        jobs = {1: {(1, 0): [Job((0, 9), 9, 3), Job((0, 2), 3, 3), Job((0, 7), 1, 1)]}}
        exterior = {"first_final": 5, "decode": 2}

        def price(**kwargs):
            return M["bounds"](calls, jobs, exterior, **kwargs)["first_final"]

        self.assertEqual(price(), 17)
        self.assertEqual(price(bank={(0, 2)}, direct=True), 17)
        self.assertEqual(price(bank={(0, 9)}), 11)
        self.assertEqual(price(free_set=True), 14)
        self.assertEqual(price(uniform=M["MODEL_EXPERTS"]), 8)
        self.assertEqual(price(uniform=M["MODEL_EXPERTS"] // 2, direct=True), 11)
        self.assertEqual(price(uniform=M["MODEL_EXPERTS"] // 2), 13)

    def test_finite_capacity_edges(self):
        for target in (0, 1, 353, M["MODEL_EXPERTS"]):
            self.assertEqual(M["min_capacity"](lambda n, target=target: n >= target), target)
        self.assertIsNone(M["min_capacity"](lambda _: False))


if __name__ == "__main__":
    unittest.main()
