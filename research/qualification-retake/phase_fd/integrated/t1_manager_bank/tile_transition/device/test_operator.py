import hashlib
import struct
import tempfile
import unittest
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
check = run_path(str(HERE / "review.py"))["check_child"]
sample = run_path(str(HERE.parent / "test_review.py"))["sample"]


class Operator(unittest.TestCase):
    def test_gold_discrimination_and_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = Path(tmp)
            row, gold = sample("reference")
            row["status"] = "PASS_C291_TILE_TRANSITION_CUDA"
            row["operator_rows"] = {}
            for key, value, ids in (
                ("reader", 1, [0, 1, 6, 4]),
                ("old-gold", 1, [0, 1, 6, 4]),
                ("new-gold", 2, [3, 5, 0, 2]),
                ("decode", 3, [6, 7, 2, 4]),
            ):
                raw = struct.pack("<2880f", *([value] * 2880))
                (case / (key + ".f32")).write_bytes(raw)
                row["operator_rows"][key] = {
                    "floats": 2880,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "ids": ids,
                    "mask": [1] * 4 if key == "decode" else [0, 0, 1, 1],
                    "mmid": 3,
                    "original_operands": 3,
                    "device": "CUDA0",
                    "event": False,
                    "view": key == "reader",
                }
            self.assertEqual(
                check("reference", case, case, row, gold)["differing_gold_coordinates"], 2880
            )
            row["operator_rows"]["reader"]["original_operands"] = 2
            with self.assertRaisesRegex(ValueError, "operator"):
                check("reference", case, case, row, gold)
            row["operator_rows"]["reader"]["original_operands"] = 3
            actual = case / "reader.f32"
            raw = actual.read_bytes()
            actual.write_bytes(raw[:-4] + struct.pack("<f", 2.0))
            with self.assertRaisesRegex(ValueError, "full FFN reader"):
                check("reference", case, case, row, gold)
            actual.write_bytes(raw[:-4] + struct.pack("<f", float("nan")))
            with self.assertRaisesRegex(ValueError, "nonfinite"):
                check("reference", case, case, row, gold)


if __name__ == "__main__":
    unittest.main()
