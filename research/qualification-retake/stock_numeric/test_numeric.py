import math
import struct
import unittest

from evaluate import compare


class NumericTests(unittest.TestCase):
    def setUp(self):
        self.gold = struct.pack("<18f", *([1, 3, 3, 0, -1, -2] * 3))

    def test_complete_finite_reference_and_stable_ties(self):
        r = compare(self.gold, self.gold, 6)
        self.assertEqual(r["status"], "PASS_BITWISE_3_ROWS")
        self.assertEqual([x["position"] for x in r["rows"]], [15, 16, 17])
        self.assertEqual(r["rows"][0]["stock_top_ids"], [1, 2, 0, 3, 4])

    def test_finite_same_argmax_remains_different(self):
        x = bytearray(self.gold)
        struct.pack_into("<f", x, 3 * 4, -0.0)
        r = compare(x, self.gold, 6)
        self.assertEqual(r["status"], "FINITE_DIFFERENT_BITS_PARITY_INCONCLUSIVE")
        self.assertTrue(r["rows"][0]["greedy_equal"])
        self.assertEqual(r["rows"][0]["max_abs"], 0.0)
        self.assertEqual(r["rows"][0]["different_f32_bits_count"], 1)

    def test_nonfinite_or_incomplete(self):
        x = bytearray(self.gold)
        struct.pack_into("<3f", x, 0, math.nan, math.inf, -math.inf)
        r = compare(x, self.gold, 6)
        self.assertEqual(r["status"], "FAIL_NONFINITE")
        self.assertEqual([r["rows"][0][k] for k in ("nan", "pos_inf", "neg_inf")], [1, 1, 1])
        with self.assertRaises(ValueError):
            compare(x[:-4], self.gold, 6)


if __name__ == "__main__":
    unittest.main()
