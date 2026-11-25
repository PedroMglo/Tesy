import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

source = Path(__file__).resolve().with_name("compact.py")
spec = importlib.util.spec_from_file_location("offline_b3_compact", source)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class TestArchive(unittest.TestCase):
    def test_failed_pre_admission_has_zero_launches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "AR"
            folder.mkdir()
            (folder / "receipt.json").write_text(
                json.dumps(dict(mode="AR", status="FAIL_PRESERVED", model_launch_receipts=0))
            )
            result = c.arm_report(
                root,
                "AR",
                dict(
                    status="FAIL_PRESERVED",
                    model_launch_receipts=0,
                    receipt_sha256=c.sha(folder / "receipt.json"),
                ),
            )[0]
            self.assertEqual(result["model_launches"], 0)
            self.assertEqual(result["complete_F32_files_observed"], 0)
            (folder / "raw").mkdir()
            (folder / "raw/test.launch.json").touch()
            with self.assertRaises(ValueError):
                c.arm_report(
                    root,
                    "AR",
                    dict(
                        status="FAIL_PRESERVED",
                        model_launch_receipts=0,
                        receipt_sha256=c.sha(folder / "receipt.json"),
                    ),
                )

    def test_tree_ignores_original_location_but_not_changed_byte(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "one"
            b = Path(tmp) / "two"
            a.mkdir()
            b.mkdir()
            for root in (a, b):
                (root / "d").mkdir()
                (root / "d/data").write_bytes(b"abc")
            self.assertEqual(c.tree(a), c.tree(b))
            (b / "d/data").write_bytes(b"abd")
            self.assertNotEqual(c.tree(a), c.tree(b))
