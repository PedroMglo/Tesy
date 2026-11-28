"""Verify the prefill read populations, both cuts and receipt rejection before timing."""

import unittest
from pathlib import Path
from runpy import run_path

M = run_path(Path(__file__).with_name("prefill_io.py"))


class PrefillIO(unittest.TestCase):
    def setUp(self):
        self.plan = dict(pack_stat=[1, 2, 3, 4, 5], unique=779, counts=M["COUNTS"])
        self.lines = ["fd 1 2 3 4 5", "parity 779 5"]
        for i, m in enumerate((0, 1, 1, 0), 1):
            for j, n in enumerate(M["COUNTS"][m], 1):
                self.lines.append(f"step {i} {m} {j} {n} {(n + 3) // 4} {j} {j + 2}")
        self.lines.append("drained")

    def test_measured_inputs_and_final_drain(self):
        out = M["parse"](self.lines, self.plan)
        self.assertEqual([a["mode"] for a in out["arms"]], list("DEED"))
        self.assertEqual(out["timed_markers"], 29124)
        with self.assertRaises(ValueError):
            M["parse"](self.lines[:-1], self.plan)
        self.lines[2] = self.lines[2].replace("34 9", "33 9")
        with self.assertRaises(ValueError):
            M["parse"](self.lines, self.plan)

    def test_two_calls_share_the_original_ring_and_sha256_checks(self):
        native = M["native_source"]()
        self.assertIn("c < 2;", native)
        self.assertIn("b.verify(g);", native)
        self.assertIn("mode == 0 && step.back().offset == w.offset", native)

    def test_free_io_can_pass_device_only_with_client_still_ambiguous(self):
        timing = M["parse"](self.lines, self.plan)
        raw = dict(status="MEASURED", protocol=M["PROTO"], timing=timing, requested_B=1)
        verdict = M["grade"](raw)
        self.assertEqual(verdict["device"], "GO_CONSUMER_FIXTURE_ONLY")
        self.assertEqual(verdict["client"], "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
