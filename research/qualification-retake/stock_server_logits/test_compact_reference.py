import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import compact_reference as c
from test_compare import make_arm


class CompactReference(unittest.TestCase):
    def test_whole_file_pinned_before_selecting_one_row(self):
        data = struct.pack("<9f", 0.0, 2, 1, 9, 4, 3, 1, 2, 3)
        expected = c.digest(data)
        row = c.select_first_row(data, expected, width=3)
        self.assertEqual(row, data[:12])
        for wrong in (data[:-4], data + b"x", data[:-1] + bytes([data[-1] ^ 1])):
            with self.subTest(n=len(wrong)), self.assertRaises(ValueError):
                c.select_first_row(wrong, expected, width=3)
        neg_zero = struct.pack("<3f", -0.0, 2, 1)
        stats = c.summarize(row, neg_zero, vocab=3)
        self.assertEqual(stats["different_f32_bits"], 1)
        self.assertEqual(stats["max_abs"], 0)
        self.assertEqual(stats["candidate_argmax"], stats["gold_argmax"])
        self.assertFalse(stats["bitwise_equal"])

    def test_full_synthetic_post_exit_and_comparison_at_256_mib(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report, raw = make_arm(root, "S")
            row = (raw / "raw/row.f32").read_bytes()
            triple = row + row + row
            (root / "three.f32").write_bytes(triple)
            script = """
import resource, sys
from pathlib import Path
import compact_reference as c
resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
report, raw, hist = map(Path, sys.argv[1:4])
record, server = c.verified_row(report, raw)
three = c.bounded(hist, 3 * c.ROW_BYTES)
client = c.select_first_row(three, sys.argv[4])
del three
result = c.summarize(client, server)
assert result["bitwise_equal"] and result["candidate_argmax"] == 3
"""
            subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    script,
                    str(report),
                    str(raw),
                    str(root / "three.f32"),
                    c.digest(triple),
                ],
                cwd=c.HERE,
                check=True,
                timeout=30,
            )

    def test_provenance_pins(self):
        c.pinned(c.OLD / "physical-r1/receipt.json", c.OLD_RECEIPT_SHA, 1 << 20)
        c.pinned(c.OLD / "build-r2/receipt.json", c.BUILD_SHA, 1 << 20)
        c.pinned(c.HERE / "compact-reference.md", c.PROTOCOL_SHA, 1 << 20)
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "receipt.json"
            other.write_bytes(b"{}")
            with self.assertRaises(ValueError):
                c.pinned(other, c.S_RECEIPT_SHA, 1 << 20)

    def test_cross_run_settings_are_required(self):
        build = {"own_libraries": {"libllama.so.0": c.STOCK}, "stock_build_receipt_sha256": "stock"}
        prompt = {"prompt_ids_sha256": "prefix", "packed_18_ids_sha256": "supplied"}
        history = {
            "model_sha256": c.MODEL_SHA,
            "c118": {"cap_bytes": 10 << 30},
            "input_sha256": "supplied",
        }
        s = {
            "arm": "S",
            "warmup_requested": False,
            "model": {"sha256": c.MODEL_SHA},
            "build_receipt_sha256": "stock",
            "stock_libllama_sha256": c.STOCK,
            "active_libllama_sha256": c.STOCK,
            "cap_bytes": 10 << 30,
            "scope": "FULL_SWA_C110_FIRST_16_SINGLE_GREEDY_TOKEN",
            "mapped_own_libraries": ["libllama.so.0"],
            "ready_log_geometry": dict.fromkeys(
                ("full_kv", "full_swa_mode", "swa_kv", "group", "slot", "ready"), True
            ),
            "ready_vma": dict.fromkeys(
                ("observer_present", "gguf", "active_libllama_present", "other_libllama_absent"),
                True,
            ),
            **prompt,
        }
        c.check_pair(s, history, build, prompt)
        for field, val in (
            ("arm", "A"),
            ("cap_bytes", 20 << 30),
            ("prompt_ids_sha256", "other"),
            ("ready_log_geometry", s["ready_log_geometry"] | {"full_swa_mode": False}),
            ("active_libllama_sha256", "candidate"),
            ("mapped_own_libraries", []),
        ):
            with self.subTest(field=field), self.assertRaises(ValueError):
                c.check_pair(s | {field: val}, history, build, prompt)


if __name__ == "__main__":
    unittest.main()
