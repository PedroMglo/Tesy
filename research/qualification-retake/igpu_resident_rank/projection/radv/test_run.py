"""Check a one-ULP failure, a wrong slot, nonfinite output and packed RHS offsets."""

import struct
import unittest
from pathlib import Path
from runpy import run_path

compare = run_path(Path(__file__).with_name("run.py"))["compare"]


class E28Projection(unittest.TestCase):
    def setUp(self):
        self.gold = struct.pack("<I", 0x3F800000) * 2880
        self.wrong = bytes(11520)
        self.cpu = bytes(3060)
        self.gpu = bytearray(3312)

    def score(self, value):
        return compare(value, self.wrong, self.gold, self.gpu, self.cpu)

    def test_exact_and_one_ulp(self):
        self.assertEqual(self.score(self.gold)["decision"], "GO_NEXT_PROJECTION_ONLY")
        got = self.score(self.gold[:-4] + struct.pack("<I", 0x3F7FFFFF))
        self.assertEqual((got["first_unequal"], got["max_ulp"]), (2879, 1))
        self.assertEqual(got["decision"], "NO_GO_BITWISE_STOCK_PROJECTION")

    def test_rhs_inner_outer(self):
        self.gpu[144 + 4] = 2
        self.gpu[144 + 16 + 32 + 31] = 3
        result = self.score(self.gold)
        self.assertEqual(result["first_scale_block"], 5)
        self.assertEqual(result["first_code_coordinate"], [5, 31])
        self.gpu[-1] = 1
        with self.assertRaises(ValueError):
            self.score(self.gold)

    def test_controls(self):
        with self.assertRaises(ValueError):
            self.score(self.gold[:-4] + struct.pack("<f", float("nan")))
        self.wrong = self.gold
        with self.assertRaises(ValueError):
            self.score(self.gold)


if __name__ == "__main__":
    unittest.main()
