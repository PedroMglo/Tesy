"""Portable resource-free checks for the two synthetic source layouts and failed-commit seam."""

import tempfile
import unittest
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
R = run_path(HERE / "run.py")


class Fixture(unittest.TestCase):
    def test_two_sparse_layouts(self):
        with tempfile.TemporaryDirectory() as parent:
            loc = Path(parent) / "new"
            files = R["materialize"](loc)
            self.assertEqual(files["pack.test"]["size"], 6 * R["D"])
            for e in range(6):
                for k in range(3):
                    for off, n in (
                        (e * R["D"] + k * R["S"], "pack.test"),
                        (k * R["G"] + e * R["S"], "gguf.test"),
                    ):
                        with (loc / n).open("rb") as f:
                            f.seek(off)
                            self.assertEqual(f.read(3), bytes([16 * e + k + 1, 0, 0]))
                            f.seek(off + R["S"] - 2)
                            self.assertEqual(f.read(2), bytes([0, 16 * e + k + 81]))

    def test_overlay_preserves_commit_and_consumer(self):
        added = "\n".join(
            x[1:]
            for x in (HERE / "observer.patch").read_text().splitlines()
            if x.startswith("+") and not x.startswith("+++")
        )
        self.assertIn("pfj::loaded(valid);", added)
        self.assertNotIn("pfj::loaded(ok);", added)
        self.assertIn("pfj::journal ? pfj::pack_read : ::pread", added)
        for intrusive in ("ggml_backend_synchronize(", "cudaEvent", "set_eval_callback("):
            self.assertNotIn(intrusive, added)


if __name__ == "__main__":
    unittest.main()
