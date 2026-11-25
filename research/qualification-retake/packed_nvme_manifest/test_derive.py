import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import derive as d  # noqa: E402


class Derivation(unittest.TestCase):
    def test_only_two_index_fields_can_change(self):
        original = {
            "pack_path": "old",
            "model_stat": {},
            "experts": [{"components": [{"sha256": "a"}]}],
        }
        changed = {"pack_path": "new", "model_stat": {"dev": 7}}
        d.validate_changes(original, original | changed, changed, d.INDEX_FIELDS)
        for bad in [
            original | changed | {"experts": []},
            original | changed | {"unknown": 0},
            {k: v for k, v in (original | changed).items() if k != "experts"},
        ]:
            with self.assertRaises(ValueError):
                d.validate_changes(original, bad, changed, d.INDEX_FIELDS)
        with self.assertRaises(ValueError):
            d.validate_changes(
                original, original | changed, changed | {"experts": []}, d.INDEX_FIELDS
            )

    def test_placement_requires_both_verifications(self):
        p = dict(
            status="PASS_NVME_C290_FULL_PACK_PLACEMENT",
            program_sha256=d.PLACER_SHA,
            protocol_sha256=d.PLACER["METHOD"],
            source_sha256=d.PLACER["DIGEST"],
            destination_sha256=d.PLACER["DIGEST"],
            source_read_bytes=d.PLACER["SIZE"],
            destination_write_bytes=d.PLACER["SIZE"],
            destination_reread_bytes=d.PLACER["SIZE"],
            size_bytes=d.PLACER["SIZE"],
            source_transport="usb",
            destination_transport="nvme",
            runtime_manifest_sha256=d.PLACER["MANIFEST"],
            index_sha256=d.PLACER["INDEX"],
            readback_sha256=d.PLACER["READBACK"],
            readback_analysis_sha256=d.PLACER["READBACK_ANALYSIS"],
        )
        d.check_placement(p)
        for key, val in [
            ("status", "FAIL_PRESERVED"),
            ("destination_reread_bytes", 0),
            ("readback_sha256", d.PLACER["READBACK_ANALYSIS"]),
            ("destination_transport", "usb"),
            ("program_sha256", "other"),
        ]:
            with self.assertRaises(ValueError):
                d.check_placement(p | {key: val})

    def test_metadata_publication_is_exclusive(self):
        with tempfile.TemporaryDirectory() as temp:
            f = Path(temp) / "metadata"
            d.save(f, {"experts": []})
            self.assertFalse(f.stat().st_mode & 0o222)
            self.assertEqual({"experts": []}, d.load(f, d.sha(f)))
            self.assertEqual(d.runtime_stat(f.stat())["inode"], f.stat().st_ino)
            with self.assertRaises(FileExistsError):
                d.save(f, {"experts": [3]})
            link = f.with_name("link")
            os.symlink(f, link)
            with self.assertRaises(ValueError):
                d.load(link, d.sha(f))


if __name__ == "__main__":
    unittest.main()
