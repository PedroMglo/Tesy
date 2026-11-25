import unittest
from pathlib import Path
from runpy import run_path

import numpy as np

S = run_path(str(Path(__file__).with_name("score.py")))


class Rounding(unittest.TestCase):
    def test_ties_carry_sign_and_subnormal(self):
        src = [
            0x00000000,
            0x80000000,
            0x00000001,
            0x00003000,
            0x3F801000,
            0x3F801001,
            0x3F803000,
            0xBF801000,
            0xBF803000,
            0x3FFFFFFF,
        ]
        target = [
            0x00000000,
            0x80000000,
            0x00000000,
            0x00004000,
            0x3F800000,
            0x3F802000,
            0x3F804000,
            0xBF800000,
            0xBF804000,
            0x40000000,
        ]
        self.assertEqual(
            S["rounded"](np.array(src, dtype="<u4").view("<f4")).view("<u4").tolist(), target
        )
        with self.assertRaises(ValueError):
            S["rounded"](np.array([0x7F7FFFFF], dtype="<u4").view("<f4"))

    def test_only_wide_device(self):
        params = [
            (None, np.array([[1.0004]], dtype="<f4"), np.zeros(1, dtype="<f4")) for _ in range(36)
        ]
        fn = S["surrogate"](params)
        for layer, n, exact in ((24, 32, False), (25, 29, True), (25, 32, True), (35, 1, False)):
            _, w, b = params[layer]
            x = np.full((n, 1), 1.0004, dtype="<f4")
            out, _ = fn(x, w, b)
            self.assertEqual(bool(np.all(out == 1)), exact)


if __name__ == "__main__":
    unittest.main()
