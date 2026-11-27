import unittest
from pathlib import Path
from runpy import run_path

M = run_path(str(Path(__file__).with_name("residency.py")))
Call = M["BASE"]["Call"]
Job = M["Job"]


class ResidentWeights(unittest.TestCase):
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
