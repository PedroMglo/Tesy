import hashlib
import struct
import tempfile
import unittest
from pathlib import Path

import fixture


class CaptureFixtureTests(unittest.TestCase):
    def test_reference_shape_and_same_argmax_mutant(self):
        control = fixture.expected_row()
        candidate = fixture.expected_row(changed=True)
        self.assertEqual(len(control), 201088 * 4)
        self.assertEqual(control[:4], bytes.fromhex("00000080"))
        self.assertEqual(control[: 123 * 4], candidate[: 123 * 4])
        self.assertEqual(control[124 * 4 :], candidate[124 * 4 :])
        for data in (control, candidate):
            vals = struct.unpack("<201088f", data)
            self.assertEqual(max(vals), 100.0)
            self.assertEqual(vals.index(max(vals)), 4567)
        self.assertNotEqual(hashlib.sha256(control).digest(), hashlib.sha256(candidate).digest())

    def test_arm_is_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            fixture.arm(path)
            before = (path / "ARM").stat()
            self.assertEqual((path / "ARM").read_bytes(), b"tesy-first-prompt16-v1\n")
            with self.assertRaises(FileExistsError):
                fixture.arm(path)
            self.assertEqual(before.st_ino, (path / "ARM").stat().st_ino)

    def test_contract_requires_real_elf_and_negative_cases(self):
        self.assertEqual(fixture.CASES["duplicate"], fixture.CASES["concurrent"])
        self.assertEqual(fixture.CASES["two_rows"], "multiple_rows_or_nonraw")
        self.assertEqual(fixture.CASES["short_vocab"], "vocab_shape")
        self.assertEqual(fixture.CASES["lost_arm"], "invalid_seal_arm")
        self.assertEqual(
            [k for k, v in fixture.CASES.items() if v == "PASS"], ["normal", "same_argmax"]
        )


if __name__ == "__main__":
    unittest.main()
