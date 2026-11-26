import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grade  # noqa: E402


class GradeTests(unittest.TestCase):
    def test_sentinel_population_matches_native_witness_scope(self):
        r = {"phase": "prefill0", "layer": "0", "name": "ffn_moe_wave_ids"}
        self.assertTrue(grade.sentinel_scope(r))
        self.assertTrue(grade.sentinel_scope(r | {"phase": "decode0", "layer": "35"}))
        for change in ({"phase": "prefill128"}, {"layer": "1"}, {"name": "ffn_moe_topk"}):
            self.assertFalse(grade.sentinel_scope(r | change))

    def test_accepted_stdout_rejects_truncation_duplicate_and_false_sentinel_count(self):
        phases = zip(grade.LABELS, (2247, 2499, 2751, 3003, 3255), strict=True)
        lines = ["C80_CONTEXT_READY ngl=12 case=log_medium ctx=8192 preload=on kv_unified=1"]
        lines += [f"captured={phase} tensors={n}" for phase, n in phases]
        lines.append(
            "capture_tensors=3255 bytes=84291920 checked_slices=996 checked_bytes=2200124160 "
            "sentinel_pairs=896 prompt_ids=189 continuation_ids=43 masked_states=2"
        )
        transcript = "\n".join(lines)
        self.assertEqual(grade.stdout_counts(transcript)["checked_slices"], 996)
        for bad in (
            "\n".join(lines[1:]),
            transcript + "\n" + lines[-1],
            transcript.replace("sentinel_pairs=896", "sentinel_pairs=895"),
        ):
            with self.assertRaisesRegex(ValueError, "transcript"):
                grade.stdout_counts(bad)

    def test_missing_c127_and_same_capture_do_not_grade(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "same capture"):
                grade.check_pair(root, root)
            with self.assertRaisesRegex(ValueError, "C127 bridge"):
                grade.check_arm(root, root, root, {})
            (root / "item").write_bytes(b"fixture")
            (root / "link").symlink_to(root / "item")
            with self.assertRaisesRegex(ValueError, "indirect"):
                grade.regular_files(root)

    def test_logit_hashes_include_signed_zero_and_reject_a_short_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for label in grade.LABELS:
                (root / (label + ".logits.f32")).write_bytes(bytes(4 * grade.VOCAB))
            first = grade.logits(root)
            path = root / "decode31.logits.f32"
            with path.open("r+b") as out:
                out.seek(-4, os.SEEK_END)
                out.write(struct.pack("<f", -0.0))
            second = grade.logits(root)
            self.assertEqual([k for k in first if first[k] != second[k]], ["decode31"])
            path.write_bytes(b"")
            with self.assertRaisesRegex(ValueError, "incomplete"):
                grade.logits(root)

    def test_qualified_mismatch_distinct_from_invalid_witness(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second = (Path(tmp) / name for name in ("off", "on"))
            first.mkdir()
            second.mkdir()
            with patch.object(
                grade.strong,
                "compare",
                side_effect=ValueError("same-profile transport payload differs: core"),
            ):
                with self.assertRaises(grade.FidelityMismatch):
                    grade.compare(second, first)
            with patch.object(grade.strong, "compare", side_effect=ValueError("invalid witness")):
                with self.assertRaisesRegex(ValueError, "invalid witness") as got:
                    grade.compare(second, first)
                self.assertNotIsInstance(got.exception, grade.FidelityMismatch)


if __name__ == "__main__":
    unittest.main()
