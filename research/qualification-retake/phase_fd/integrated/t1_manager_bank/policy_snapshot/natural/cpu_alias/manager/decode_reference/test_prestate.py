import struct
import unittest
from pathlib import Path
from runpy import run_path

m = run_path(Path(__file__).with_name("prestate.py"))


class TestState(unittest.TestCase):
    def test_skips_padding(self):
        b = struct.pack("<4i", 8, 28, 16, 15) + b"\xff" * 496 + struct.pack("<4i", 28, 103, 17, 127)
        rows = m["ranks"](b, 2, (4, 512))
        self.assertEqual(rows[1], (28, 103, 17, 127))
        with self.assertRaises(ValueError):
            m["ranks"](b, 2, (4, 16))

    def test_ready_identity_and_distinct_missing(self):
        keys = [28, 24, 8, 16]
        records = [dict(expert=e, capture_slot=i, capture_generation=3) for i, e in enumerate(keys)]
        pre = [
            {
                "expert": str(e),
                "class": "READY" if e != 24 else "ABSENT_RELOAD",
                "slot": str(i) if e != 24 else "-1",
                "generation": "3" if e != 24 else "0",
            }
            for i, e in enumerate(keys)
        ]
        self.assertEqual(
            [r["state_before"] for r in m["annotate"](pre, records, set(keys) - {24})].count(
                "READY"
            ),
            3,
        )
        pre[0]["slot"] = "22"
        with self.assertRaisesRegex(ValueError, "READY"):
            m["annotate"](pre, records, set(keys))


if __name__ == "__main__":
    unittest.main()
