import hashlib
import tempfile
import unittest
from pathlib import Path

from run import prerequisite, route


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
