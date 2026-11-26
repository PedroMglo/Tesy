import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run  # noqa: E402


class TestRouter(unittest.TestCase):
    def test_corruption_and_signed_zero(self):
        row = struct.pack("<128f", *range(128))
        sw = row[4:8] + row[:4] + row[8:]
        run.control(row * 3, sw * 3)
        self.assertEqual(run.difference(row * 3, sw * 3), 6)
        with self.assertRaises(ValueError):
            run.control(row * 3, sw * 2 + row)
        self.assertEqual(run.difference(struct.pack("<f", 0), struct.pack("<f", -0.0)), 1)


if __name__ == "__main__":
    unittest.main()
