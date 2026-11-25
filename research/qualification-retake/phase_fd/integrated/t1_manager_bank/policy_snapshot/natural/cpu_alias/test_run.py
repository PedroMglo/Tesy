"""The expected fault controls must be distinguishable from guard failures."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import PAGE, WINDOW, grade


class TestArms(unittest.TestCase):
    stat = SimpleNamespace(st_dev=7, st_ino=19)

    def measurements(self, mode):
        return {
            "arm": mode,
            "status": "PASS",
            "reader_old": int(mode != "early"),
            "bank_old": int(mode != "reuse"),
            "restored_old": int(mode != "reuse"),
            "new_primary_correct": True,
            "short_published": False,
            "source_dev": 7,
            "source_ino": 19,
            "preads": 3,
            "returned_bytes": 2 * WINDOW + PAGE,
            "short_returned_bytes": PAGE,
            "backing_before_alias": WINDOW,
            "backing_after_alias": WINDOW,
            "arena_virtual_bytes": 40 * WINDOW + 3 * PAGE,
            "maxrss_kib": 40 * 1024,
        }

    def test_exact_outcomes(self):
        for mode in ("safe", "early", "reuse"):
            with self.subTest(mode=mode):
                grade(self.measurements(mode), mode, self.stat)

    def test_negative_control_must_expose_expected_damage(self):
        for mode, key in [("safe", "bank_old"), ("early", "reader_old"), ("reuse", "restored_old")]:
            arm = self.measurements(mode)
            arm[key] ^= 1
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                grade(arm, mode, self.stat)

    def test_reject_duplicate_backing_or_published_short_completion(self):
        for key, value in [
            ("backing_after_alias", 2 * WINDOW),
            ("short_published", True),
            ("source_ino", 20),
            ("preads", 4),
            ("short_returned_bytes", 0),
        ]:
            arm = self.measurements("safe")
            arm[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError):
                grade(arm, "safe", self.stat)


if __name__ == "__main__":
    unittest.main()
