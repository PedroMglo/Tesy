import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

from run import prerequisite, route, stage_witness


class Gates(unittest.TestCase):
    def test_route_and_parking(self):
        for n in (1, 32, 3):
            for p in range(n):
                ids = [route(n, p, r) for r in range(4)]
                self.assertEqual(len(set(ids)), 4)
                self.assertTrue(all(0 <= x < 40 for x in ids))
                if n == 3:
                    self.assertEqual(ids[2:], [36, 37])
                else:
                    self.assertIn(39, ids)

    def test_prerequisite_must_match_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "gate.json"
            p.write_bytes(b"{}")
            sha = hashlib.sha256(b"{}").hexdigest()
            self.assertEqual(prerequisite(p, sha), {})
            p.write_bytes(b"{}\n")
            with self.assertRaisesRegex(ValueError, "digest"):
                prerequisite(p, sha)

    def test_masked_alias_reproduces_the_stale_check(self):
        n = 3
        before = bytearray(n * 4 * 2880 * 4)
        first = 2 * 2880
        struct.pack_into("<f", before, 4 * first, -17.0)
        after = bytearray(before)
        struct.pack_into("<f", after, 4 * first, -0.0)
        a, b = (hashlib.sha256(x).hexdigest() for x in (before, after))
        mask = hashlib.sha256(struct.pack("<12f", *([1, 1, 0, 0] * 3))).hexdigest()
        words = [
            "dense",
            "3",
            "0",
            "1",
            "1",
            a,
            a,
            mask,
            b,
            b,
            "1",
            "0",
            str(first),
            str(struct.unpack_from("<I", before, 4 * first)[0]),
            str(0x80000000),
        ]

        def verify(w):
            return stage_witness(" ".join(w), "dense", n, 0, before, after)

        self.assertEqual(verify(words)["first_late_v2_difference"]["rank"], 2)
        for i, v in ((6, b), (7, a), (8, a), (9, a), (10, "0"), (11, "1"), (12, "0"), (14, "0")):
            wrong = words.copy()
            wrong[i] = v
            with self.subTest(field=i), self.assertRaises(ValueError):
                verify(wrong)
        # Distinct addresses in the same buffer can retain the original input.
        no_alias = words.copy()
        no_alias[4] = "0"
        no_alias[8] = a
        no_alias[10:] = ["0", "0", "-1", "0", "0"]
        self.assertFalse(verify(no_alias)["same_address"])
