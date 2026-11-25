import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run import compare_positions, words  # noqa: E402


class Grade(unittest.TestCase):
    def test_one_bit_and_signed_zero(self):
        clean = struct.pack("<III", 0, 0x3F800000, 0x3F810000)
        wrong = struct.pack("<III", 0x80000000, 0x3F800001, 0x3F810000)
        self.assertEqual(
            words(clean, wrong),
            {"changed": 2, "first": {"index": 0, "reference": "00000000", "candidate": "80000000"}},
        )
        self.assertEqual(words(clean, clean)["changed"], 0)

    def test_position_permutation_does_not_permute_ranks(self):
        original = b"abcDefgHijkL"
        self.assertEqual(compare_positions(original, 4, (2, 0, 1)), b"ijkLabcDefgH")
        self.assertNotEqual(compare_positions(original, 4, (2, 0, 1)), b"jikLabcDefgH")
        with self.assertRaises(ValueError):
            compare_positions(original[:-1], 4, (2, 0, 1))


if __name__ == "__main__":
    unittest.main()
