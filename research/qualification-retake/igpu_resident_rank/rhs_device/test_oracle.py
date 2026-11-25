import hashlib
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402


def wire(first_code):
    # Independent literal wire image of the three active blocks, including signs.
    result = bytearray(3312)
    first_sum = 0x498B if first_code == 1 else 0x4996
    result[:12] = struct.pack("<6H", 0x2D8B, first_sum, 0x2D8B, 0x4996, 0x3C00, 0x57C0)
    result[16:18] = bytes([127, first_code])
    result[48:50] = bytes([127, 2])
    result[80:82] = bytes([127, 253])
    return result


class TestOracle(unittest.TestCase):
    def test_input_words_and_extent(self):
        data = oracle.inputs()
        self.assertEqual(len(data), 11520)
        words = struct.unpack("<2880I", data)
        self.assertEqual(
            [(i, x) for i, x in enumerate(words) if x],
            [
                (0, 0x41300000),
                (1, 0x3E050A14),
                (32, 0x41300000),
                (33, 0x3E400000),
                (64, 0x42FE0000),
                (65, 0xC0400000),
            ],
        )
        self.assertEqual(
            hashlib.sha256(data).hexdigest(),
            "945d5bff8d78d0de8bfad30db658e92e7f7c7a2027fba43035350cca1d0c485b",
        )

    def test_both_models_and_dependent_sum(self):
        for code, verdict in [(1, oracle.LITERAL), (2, oracle.CPU)]:
            result = oracle.grade(wire(code))
            self.assertEqual(result["verdict"], verdict)
            self.assertEqual(result["codes"], [code, 2])
            self.assertEqual(result["scale_f16_bits"], ["2d8b", "2d8b", "3c00"])
            self.assertEqual(result["sum_f16_bits"][-1], "57c0")
        stale_sum = wire(1)
        stale_sum[17] = 2
        with self.assertRaises(ValueError):
            oracle.grade(stale_sum)

    def test_sign_layout_padding_and_sentinels(self):
        for offset in (0, 4, 81, 130, 144, 3300, 3311):
            raw = wire(1)
            raw[offset] ^= 0x20
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                oracle.grade(raw)
        for raw in (b"", bytes(3311), bytes(3313), b"\0" * 3312, bytes([0xA5]) * 3312):
            with self.assertRaises(ValueError):
                oracle.grade(raw)


if __name__ == "__main__":
    unittest.main()
