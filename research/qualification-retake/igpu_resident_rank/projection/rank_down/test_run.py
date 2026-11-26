"""Shape, precision, alternate expert and prospective native source checks."""

import struct
import tempfile
import unittest
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
R = run_path(HERE / "run.py")


class RankDown(unittest.TestCase):
    def test_arithmetic(self):
        y = struct.pack("<f", 1.0) * 2880
        alt = struct.pack("<f", 1.5) * 2880
        self.assertEqual(R["assess"](y, alt, y)["control_changed_words"], 2880)
        self.assertEqual(R["assess"](alt, y, y)["decision"], "NO_GO_RANK_DOWN_BITWISE")
        for a, b in ((y, y), (y[:-4], alt), (struct.pack("<f", float("nan")) + y[4:], alt)):
            with self.assertRaises(ValueError):
                R["assess"](a, b, y)

    def test_down_only(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            R["B"]["sources"](out)
            allocator = (out / "primary.inc").read_text()
            self.assertIn("ggml_backend_tensor_set", allocator)
            self.assertEqual(allocator.count("for(int r=0,k=1;r<2;r++)"), 2)
            proj = (out / "projection.inc").read_text()
            self.assertIn("cache.select(0);emit(1,args[7]);cache.release_after_fence();", proj)
            self.assertIn("cache.select(1);emit(1,args[8]);cache.release_after_fence();", proj)
            self.assertEqual(proj.count("emit(1,"), 2)


if __name__ == "__main__":
    unittest.main()
