"""Failures are validated from tiny local files, without any model or historic raws."""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

# Support both unittest discovery and the fully qualified module invocation.
product = (
    import_module(".product_reference", __package__)
    if __package__
    else import_module("product_reference")
)


class ProductReferenceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.history = self.root / "history"
        self.history.mkdir()
        self.output = self.root / "output"

    def run_check(self):
        args = [
            "product_reference.py",
            "--historical-results",
            str(self.history),
            "--new-output-dir",
            str(self.output),
        ]
        with patch.object(sys, "argv", args), redirect_stdout(io.StringIO()):
            return product.main()

    def receipt(self):
        return json.loads((self.output / "receipt.json").read_bytes())

    def test_missing_raw_records_not_run(self):
        self.assertEqual(self.run_check(), 1)
        receipt = self.receipt()
        self.assertEqual(receipt["status"], "NOT_RUN_RAW_REQUIRED")
        self.assertEqual(
            receipt["missing_file"], product.tokens_file(self.history, product.C132).name
        )

    def test_wrong_raw_digest_records_failure_and_preserves_failure_on_retry(self):
        bad = product.tokens_file(self.history, product.C132)
        bad.parent.mkdir(parents=True)
        bad.write_bytes(b"{}\n")
        self.assertEqual(self.run_check(), 1)
        receipt = self.receipt()
        self.assertEqual(receipt, {"status": "FAIL", "reason": f"SHA-256 mismatch in {bad.name}"})
        original = (self.output / "receipt.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_check()
        self.assertEqual((self.output / "receipt.json").read_bytes(), original)

    def test_missing_authoritative_decision_records_failure(self):
        with patch.object(product, "ROOT", self.root):
            self.assertEqual(self.run_check(), 1)
        self.assertEqual(self.receipt(), {"status": "FAIL", "missing_file": "decision.json"})

    def test_changed_authoritative_decision_records_failure(self):
        decision = self.root / "results" / product.C132 / "decision.json"
        decision.parent.mkdir(parents=True)
        decision.write_bytes(b'{"status":"PASS"}\n')
        with patch.object(product, "ROOT", self.root):
            self.assertEqual(self.run_check(), 1)
        self.assertEqual(
            self.receipt(), {"status": "FAIL", "reason": "SHA-256 mismatch in decision.json"}
        )


if __name__ == "__main__":
    unittest.main()
