import struct
import sys
import tempfile
import unittest
from pathlib import Path

UNIT = Path(__file__).resolve().parent
sys.path.insert(0, str(UNIT))
import profile as acquisition  # noqa: E402

import build  # noqa: E402
import grade  # noqa: E402
import render  # noqa: E402
from schema import POSITIONS, Site, population  # noqa: E402


class BoundaryTests(unittest.TestCase):
    def test_frozen_bridge_and_scope(self):
        self.assertEqual(grade.old_rows()["B3"]["mode"], "B3")
        self.assertEqual(acquisition.parent().PROTOCOL, acquisition.PROTOCOL)
        self.assertEqual(grade.sha(UNIT / "protocol.md"), acquisition.PROTOCOL)
        self.assertIn(b"test_boundary_stride();", render.render())
        self.assertIn("run", build.qualified_builder())
        self.assertEqual(len(list(population())), 295)
        self.assertEqual(grade.word_diff(struct.pack("<f", 0), struct.pack("<f", -0.0)), (1, 0))

    def test_coverage_ties_positions_and_corruption(self):
        cuts = [(0, k, Site(k, 2, (2,), ("ADD",))) for k in ("left", "right")]
        with tempfile.TemporaryDirectory() as tmp:
            dirs = [Path(tmp) / mode for mode in ("AR", "B3")]
            for arm, mode in zip(dirs, ("AR", "B3"), strict=True):
                d = arm / "boundary"
                d.mkdir(parents=True)
                width = 1 if mode == "AR" else 3
                (d / "geometry.tsv").write_text(
                    "".join(
                        f"{p}\t{width}\t{k}\tADD\t2\t{width}\t1\t1\t4\t8\t24\t24\n"
                        for p in (POSITIONS if width == 1 else [189])
                        for _, k, _ in cuts
                    )
                )
                for p in POSITIONS:
                    for _, k, _ in cuts:
                        (d / f"{p}.{k}.bin").write_bytes(
                            struct.pack("<2f", p, 1 if mode == "B3" and p == 190 else 0)
                        )
            rows = grade.compare(*dirs, cuts)
            self.assertEqual([r["site"] for r in rows["first"]], ["left", "right"])
            self.assertIsNone(rows["per_position"]["189"])
            data = dirs[1] / "boundary" / "190.right.bin"
            data.write_bytes(struct.pack("<2f", float("nan"), 0))
            with self.assertRaisesRegex(ValueError, "nonfinite"):
                grade.check_arm(dirs[1], "B3", cuts)
            data.unlink()
            with self.assertRaisesRegex(ValueError, "cut file"):
                grade.check_arm(dirs[1], "B3", cuts)
            with self.assertRaisesRegex(ValueError, "logical ordered ranks"):
                grade.validate_words(
                    struct.pack("<4i", 3, 2, 3, 1), Site("ids", 1, (4,), ("VIEW",), "I32")
                )


if __name__ == "__main__":
    unittest.main()
