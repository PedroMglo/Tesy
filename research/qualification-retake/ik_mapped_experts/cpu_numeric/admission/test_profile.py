"""Small gate tests, with full reference words only in the numerical comparator."""

import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import profile as p

from authority import GIB, select


def window(cap, other=20, reasons=()):
    return dict(
        memory={"cap_max_bytes": cap * GIB},
        canonical_memory={"cap_max_bytes": other * GIB},
        reason=list(reasons),
        status="NOT_ADMITTED" if reasons else "PASS_RESOURCE_WINDOW_ONLY",
        model_bytes_read=0,
        r0_launch="NOT_RUN",
    )


class Admission(unittest.TestCase):
    def test_both_witnesses(self):
        only = ("HOST_CAP_PLUS_RESERVE_UNAVAILABLE",)
        self.assertEqual(select(window(20)), 20)
        self.assertEqual(select(window(19.25, 20, only)), 10)
        self.assertEqual(select(window(20, 19.25, ("C55_CAP_UNAVAILABLE",))), 10)
        for w in (window(9.75, 20, only), window(19.25, 20, ("POWER",)), window(19.25)):
            with self.assertRaises(ValueError):
                select(w)

    def test_deadline_and_join(self):
        def row(labels):
            return "".join(f"PHASE {k} {i + 10}\n" for i, k in enumerate(labels))

        self.assertEqual(len(p.deadlines(row(p.PHASES), 1, 21, completed=True)), 10)
        for stream, clock in [
            (row(p.PHASES[:2]), 181_000_000_000),
            (row(p.PHASES[:5]), 91_000_000_020),
            (row(p.PHASES[:-1]), 16_000_000_100),
            (row(p.PHASES[::-1]), 100),
        ]:
            with self.assertRaises(ValueError):
                p.deadlines(stream, 1, clock)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            p.deadlines(row(p.PHASES[:8]), 1, 21, completed=True)

    def test_equal_values_different_bits(self):
        a = bytearray(p.ROW)
        struct.pack_into("<f", a, 40, 3.0)
        b = bytearray(a)
        struct.pack_into("<I", b, 4, 0x80000000)
        score = p.compare(a, b)
        self.assertEqual(
            (score["different_words"], score["max_abs"], score["top5"][0], score["ties"]),
            (1, 0, 10, 1),
        )
        struct.pack_into("<f", a, 0, float("nan"))
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            p.compare(a, b)


if __name__ == "__main__":
    unittest.main()
