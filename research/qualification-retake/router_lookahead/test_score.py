import struct
import unittest
from pathlib import Path
from runpy import run_path

import numpy as np

S = run_path(str(Path(__file__).with_name("score.py")))


class LookaheadTests(unittest.TestCase):
    def test_strided_positions_and_invalid_metadata(self):
        b = bytearray(528)
        struct.pack_into("<4i", b, 0, 6, 4, 5, 0)
        struct.pack_into("<4i", b, 512, 0, 4, 6, 5)
        row = dict(ne="4,2,1,1", nb="4,512,1024,1024", type="i32", state_tokens="2", bytes="528")
        self.assertEqual(S["matrix"](b, row, 4, "i32").tolist(), [[6, 4, 5, 0], [0, 4, 6, 5]])
        with self.assertRaises(ValueError):
            S["matrix"](b, row | {"nb": "4,16,32,32"}, 4, "i32")

    def test_gate_axis_sign_and_ties(self):
        x = np.array([[6, 1]], dtype="<f4")
        source = np.array([-2, 1], dtype="<f4")
        w = np.array([[1, 0], [-1, 0], [0, 1], [0, -1], [0, 0]], dtype="<f4")
        dest = (np.ones(2, dtype="<f4"), w, np.zeros(5, dtype="<f4"))
        self.assertEqual(S["infer"](x, source, dest).tolist(), [[1, 2, 4, 3]])
        self.assertNotEqual(S["infer"](x, abs(source), dest).tolist(), [[1, 2, 4, 3]])
        self.assertEqual(S["ranks"](np.ones((1, 5), dtype="<f4")).tolist(), [[0, 1, 2, 3]])
        with self.assertRaises(ValueError):
            S["project"](x, w.T, dest[2])
        with self.assertRaises(ValueError):
            S["infer"](x, np.zeros(2), dest)

    def test_causal_recency_and_hit_denominator(self):
        hist = {
            (1, 188): ("prefill_final", [8, 7, 6, 5]),
            (1, 189): ("decode0", [5, 6, 7, 8]),
            (1, 195): ("other", [1, 2, 3, 4]),
        }
        self.assertEqual(S["previous"](hist, 1, 189, "decode0"), [8, 7, 6, 5])
        self.assertIsNone(S["previous"](hist, 1, 189, "prefill_final"))
        self.assertIsNone(S["previous"](hist, 1, 220, "decode31"))
        m = S["metrics"]()
        actual = np.array([[3, 2, 1, 0], [4, 5, 6, 7]])
        S["count"](m, np.array([[0, 1, 2, 3], [8, 9, 6, 7]]), actual)
        self.assertEqual((m["rows"], m["hits"], m["ordered_exact"], m["set_exact"]), (2, 6, 0, 1))
        self.assertEqual(m["hits_hist"], [0, 0, 1, 0, 1])


if __name__ == "__main__":
    unittest.main()
