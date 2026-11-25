"""Exercise the launch-receipt verifier without a Vulkan runtime or GPU."""

import unittest
from pathlib import Path
from runpy import run_path

review = run_path(Path(__file__).with_name("run.py"))["review"]
JOURNAL = """scope_peak_bytes 1024
device Radeon radv 0000:c5:00.0 4098 5390 1 4096
type 5 0 14
external_features 4
queue 0 15
providers RADV+loader+renderD128
import 65536 64 32 1965 5 0 14
import 65536 64 32 1965 5 0 14
variant subgroup 1 1 64 12 2880
submit_fence_ns 208182
providers RADV+loader+renderD128
scope_peak_bytes 72351592
PASS_RHS_DISPATCH""".replace(" ", "\t")


class Dispatch(unittest.TestCase):
    def test_geometry(self):
        proof = review(JOURNAL)
        self.assertEqual(proof["push_constants"], [2880, 12])
        shared = JOURNAL.replace("subgroup\t1\t1\t64\t12", "shared\t0\t1\t32\t23")
        self.assertEqual(review(shared)["workgroups"], 23)

    def test_faults(self):
        for before, after in (
            ("subgroup", "shared"),
            ("64\t12", "64\t11"),
            ("72351592", "134217729"),
            ("renderD128", "renderD129"),
            ("32\t1965", "64\t1965"),
            ("208182", "0"),
        ):
            with self.subTest(before=before), self.assertRaises(ValueError):
                review(JOURNAL.replace(before, after))


if __name__ == "__main__":
    unittest.main()
