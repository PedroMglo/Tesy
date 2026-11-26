import json
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
m = run_path(str(HERE / "screen.py"))


class FrontierTests(unittest.TestCase):
    def test_boundary_and_denominator(self):
        def price(b):
            return m["frontier"](10, b, 6, 2, bps=10**9)

        self.assertEqual(price(12)["decision"], "HEADROOM_ONLY_IN_RELAXATION")
        r = price(Fraction(23, 2))
        self.assertEqual(r["optimistic_pipeline_margin_ns"], -0.5)
        self.assertEqual(r["decision"], "NO_GO_SCHEDULE_ALONE_AT_FIXED_PRICES")
        self.assertIsNone(price(6)["minimum_useful_Bps_serial"])
        self.assertLess(price(6)["max_gap_at_fixed_bandwidth_ns"], 0)
        with self.assertRaisesRegex(ValueError, "geometry"):
            m["frontier"](10, 2, 2, 3)

    def test_conservation(self):
        def row(disk, hits):
            return {
                "all": {
                    "admissions": disk + hits,
                    "bank_hits": hits,
                    "disk_jobs": disk,
                    "primary_bytes": (disk + hits) * m["PAYLOAD"],
                    "packed_pread_bytes": disk * 13_221_888,
                }
            }

        p = dict(
            call5=row(34, 25),
            call148=row(1024, 201),
            prefill=row(1058, 226),
            decode=row(797, 399),
            restore=row(0, 0),
        )
        self.assertEqual(m["population"](p)["prefill"]["disk_jobs"], 1058)
        p["call148"] = row(1023, 201)
        with self.assertRaisesRegex(ValueError, "bridge"):
            m["population"](p)
        p["call148"]["all"]["primary_bytes"] -= 1
        with self.assertRaisesRegex(ValueError, "primary"):
            m["population"](p)

    def test_fail_closed_and_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            f = p / "manifest.json"
            f.write_text("{}")
            with self.assertRaisesRegex(ValueError, "identity"):
                m["pinned"](f, "0" * 64)
            cmd = [
                sys.executable,
                "-IB",
                str(HERE / "screen.py"),
                "--part63",
                tmp,
                "--part66",
                tmp,
                "--new-output-dir",
                str(p / "result"),
            ]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 1)
            receipt = p / "result/receipt.json"
            old = receipt.read_bytes()
            self.assertEqual(json.loads(old)["status"], "FAIL_PRESERVED")
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertEqual(receipt.read_bytes(), old)


if __name__ == "__main__":
    unittest.main()
