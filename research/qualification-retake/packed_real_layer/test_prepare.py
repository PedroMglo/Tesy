"""Tiny synthetic counterexamples, independent of any GGUF or captured activations."""

import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import prepare as p


class TestPreparation(unittest.TestCase):
    def test_persisted_payload_and_both_padding_gaps(self):
        data = b"go" + bytes(2) + b"up!" + bytes(3)
        rows = [
            {"packed_relative_offset": 0, "size_bytes": 2, "sha256": p.sha(b"go")},
            {"packed_relative_offset": 4, "size_bytes": 3, "sha256": p.sha(b"up!")},
        ]
        p.verify_record(data, rows)
        for at in (0, 3, 5, 9):
            bad = bytearray(data)
            bad[at] ^= 1
            with self.subTest(at=at), self.assertRaises(ValueError):
                p.verify_record(bad, rows)
        with self.assertRaises(ValueError):
            p.verify_record(data, list(reversed(rows)))

    def test_fetch_charges_failed_read_and_rejects_over_budget_before_io(self):
        with tempfile.TemporaryFile() as f:
            f.write(b"0123")
            f.flush()
            r = {"gguf_read_bytes": 0, "gguf_returned_bytes": 0, "gguf_reads": 0}
            self.assertEqual(p.fetch(f.fileno(), 1, 3, p.sha(b"123"), r), b"123")
            with self.assertRaises(ValueError):
                p.fetch(f.fileno(), 1, 3, p.sha(b"124"), r)
            with self.assertRaises(ValueError):
                p.fetch(f.fileno(), 3, 3, None, r)
            self.assertEqual(
                r, {"gguf_read_bytes": 9, "gguf_returned_bytes": 7, "gguf_reads": 3}
            )
            r["gguf_read_bytes"] = p.SOURCE_BYTES
            with patch.object(
                os, "pread", side_effect=AssertionError("budget check must precede I/O")
            ):
                with self.assertRaises(ValueError):
                    p.fetch(f.fileno(), 0, 1, None, r)

    def test_routing_union_order_and_duplicate_rank(self):
        seq = [
            p.EXPERTS[0:4],
            p.EXPERTS[1:5],
            (60, 57, 49, 45),
            (49, 45, 60, 57),
            (98, 60, 57, 49),
            (45, 60, 98, 49),
            (45, 57, 98, 49),
        ]
        rows = [seq[i % 7] for i in range(153)]

        def table():
            return b"".join(struct.pack("<4i", *r) for r in rows)

        p.check_routing(table())
        rows[32] = (10, 49, 57, 60)
        with self.assertRaises(ValueError):
            p.check_routing(table())
        rows[32] = (45, 45, 49, 57)
        with self.assertRaises(ValueError):
            p.check_routing(table())

    def test_input_identity_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as parent:
            root = Path(parent)
            report = {"file_sha256": {}}
            p.write(root, "router.bias", b"abc", report)
            self.assertEqual(
                p.authenticated(root / "router.bias", p.sha(b"abc"), 3), b"abc"
            )
            with self.assertRaises(ValueError):
                p.authenticated(root / "router.bias", p.sha(b"xyz"), 3)
            with self.assertRaises(FileExistsError):
                p.write(root, "router.bias", b"xyz", report)
            self.assertEqual(report["file_sha256"], {"router.bias": p.sha(b"abc")})


if __name__ == "__main__":
    unittest.main()
