import math
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arithmetic as a  # noqa: E402
import screen  # noqa: E402


class ArithmeticTests(unittest.TestCase):
    def test_quantizer_tie_and_tiny_values(self):
        row = [11.0, struct.unpack(">f", bytes.fromhex("3e050a14"))[0], 2**-126, -0.0]
        row.extend([0.0] * (a.K - len(row)))
        q = a.quantize(struct.pack("<2880f", *row))
        self.assertEqual(q[:6], bytes.fromhex("8b2d7f020000"))
        self.assertEqual(q[34:], bytes(a.QROW - 34))
        row[3] = math.inf
        with self.assertRaises(ValueError):
            a.quantize(struct.pack("<2880f", *row))

    def test_two_accumulators_and_horizontal_grouping(self):
        weights = bytearray(a.WROW)
        q = bytearray(a.QROW)
        for b, exp, nibble in [(0, 151, 2), (1, 127, 2), (2, 151, 10), (3, 127, 2)]:
            weights[17 * b : 17 * b + 2] = bytes([exp, nibble])
            q[34 * b : 34 * b + 3] = bytes.fromhex("003c01")
        result, trace = a.dot_row(weights, a.unpack_q8(q), trace=True)
        self.assertEqual(result, struct.pack("<f", 2))
        self.assertEqual(len(trace), 90)
        self.assertEqual(trace[2][2][0], -2)
        self.assertEqual(a.FMA(1 + 2**-23, 1 - 2**-23, -1), -(2**-46))

    def test_x4_fields_and_ignored_padding(self):
        packed = bytearray(23 * 144)
        packed[144 + 4 : 144 + 8] = struct.pack("<ee", 0.25, 7)
        packed[144 + 16 + 32 + 31] = 255
        packed[-1] = 255
        unpacked = a.from_x4(packed)
        self.assertEqual(unpacked[5 * 34 : 6 * 34], struct.pack("<e", 0.25) + bytes(31) + b"\xff")
        packed[144 + 6] ^= 1
        self.assertEqual(a.from_x4(packed), unpacked)
        packed[144 + 16 + 32 + 31] ^= 1
        self.assertEqual(
            screen.delta(unpacked, a.from_x4(packed), 34), {"different": 1, "first": 5}
        )
        with self.assertRaises(ValueError):
            a.from_x4(packed[:-1])


if __name__ == "__main__":
    unittest.main()
