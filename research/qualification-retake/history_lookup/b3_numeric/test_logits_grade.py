import math
import struct
import tempfile
import unittest
from pathlib import Path

from logits_grade import N_VOCAB, ROW_BYTES, compare_rows


class Grading(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def row(self, name, prefix):
        path = self.root / name
        path.write_bytes(
            struct.pack(f"<{len(prefix)}f", *prefix) + bytes(ROW_BYTES - 4 * len(prefix))
        )
        return path

    def test_finite_row_uses_every_entry_and_preserves_signed_zero(self):
        a = self.row("reference", (3, 0, -0.0))
        b = self.row("candidate", (3, 0, 0.0))
        with b.open("r+b") as stream:
            stream.seek(-4, 2)
            stream.write(struct.pack("<f", 4))
        report = compare_rows(a, b)
        self.assertEqual((report["changed_f32_bit_patterns"], report["changed_values"]), (2, 1))
        self.assertFalse(report["same_greedy"])
        self.assertEqual(report["max_abs"], 4)
        self.assertAlmostEqual(report["rmse"], 4 / math.sqrt(N_VOCAB))

    def test_identical_tied_rows_are_not_unique_greedy_proof(self):
        a = self.row("a", (5, 5))
        report = compare_rows(a, a)
        self.assertTrue(
            report["bitwise"] and report["same_max_set"] and report["same_first_argmax"]
        )
        self.assertFalse(report["same_greedy"])
        self.assertEqual(report["reference_max_ties"], 2)
        b = self.row("b", (5, 0, 5))
        self.assertFalse(compare_rows(a, b)["same_max_set"])
        c = self.row("unique", (6, 5))
        self.assertTrue(compare_rows(c, c)["same_greedy"])

    def test_nonfinite_wrong_shape_and_links_close_the_gate(self):
        good = self.row("good", (1,))
        for i, value in enumerate((math.inf, -math.inf, math.nan)):
            with self.assertRaisesRegex(ValueError, "non-finite"):
                compare_rows(good, self.row(str(i), (value,)))
        short = self.root / "short"
        short.write_bytes(bytes(ROW_BYTES - 1))
        link = self.root / "link"
        link.symlink_to(good)
        for path in (short, link):
            with self.assertRaisesRegex(ValueError, "complete"):
                compare_rows(good, path)


if __name__ == "__main__":
    unittest.main()
