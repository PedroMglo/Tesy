import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screen import PICKS, classify, expected, output_rows, permutation, union_pages  # noqa: E402


class Coverage(unittest.TestCase):
    def test_pages_and_wrong_work(self):
        base = 512
        full = expected(base, range(128))
        self.assertEqual(full, [(0, 2097664), (2097152, 131584)])
        self.assertEqual(classify(full, base, PICKS[0]), "full")
        self.assertLess(union_pages(full), sum((size + 4095) // 4096 * 4096 for _, size in full))
        chosen = expected(base, PICKS[0])
        self.assertEqual(len(chosen), 3)
        self.assertEqual(classify(chosen, base, PICKS[0]), "selected")
        for faulty in (full[:-1], full + full[0:1], expected(base, PICKS[1])):
            with self.assertRaises(ValueError):
                classify(faulty, base, PICKS[0])

    def test_rank_permutation_and_finitude(self):
        rows = [struct.pack("<128f", *([float(i)] * 128)) for i in range(4)]
        payload = b"".join(rows)
        inp = struct.pack("<4i", *PICKS[0]) + payload
        self.assertEqual(output_rows(inp, 0, 1), [payload])
        permutation(payload, b"".join(rows[i ^ 1] for i in range(4)))
        with self.assertRaises(ValueError):
            permutation(payload, payload)
        with self.assertRaises(ValueError):
            output_rows(inp[:-4] + struct.pack("<f", float("nan")), 0, 1)


if __name__ == "__main__":
    unittest.main()
