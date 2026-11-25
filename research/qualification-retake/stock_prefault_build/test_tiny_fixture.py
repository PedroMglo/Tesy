import math
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tiny_fixture import mapped, outputs  # noqa: E402


class Tiny(unittest.TestCase):
    def test_specific_mapping_and_successful_willneed(self):
        populated = "MAP 4101 0 1 32769\nADVICE 0 4101 3 0"
        lazy = "MAP 4101 0 1 1"
        self.assertTrue(mapped(populated, 4101, False)["advice"])
        self.assertEqual(mapped(lazy, 4101, True)["advice"], [])
        for text, mode in (
            (populated, True),
            (lazy, False),
            (populated.replace("4101 3 0", "4101 3 1"), False),
            (populated.replace("0 4101 3", "1 4100 3"), False),
            (lazy + "\n" + lazy, True),
            (lazy.replace("4101", "4096"), True),
        ):
            with self.subTest(text=text, mode=mode), self.assertRaises(ValueError):
                mapped(text, 4101, mode)

    def test_compare_full_finite_rows(self):
        a = struct.pack("<32f", *range(32))
        b = struct.pack("<32f", *reversed(range(32)))
        self.assertEqual(outputs(a + b), [31, 0])
        for bad in (a, a + a, a + b[:-4] + struct.pack("<f", math.nan), a + bytes(128)):
            with self.assertRaises(ValueError):
                outputs(bad)


if __name__ == "__main__":
    unittest.main()
