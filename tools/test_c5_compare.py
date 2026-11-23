"""Model-free malformed-evidence fixtures for the C5 numerical comparator."""

import math
from pathlib import Path
import struct
import tempfile
import unittest

from c5_compare import EvidenceError, metadata, pair, validate_blob, validate_records, write_new


class CompareFixtures(unittest.TestCase):
    def setUp(self):
        self.data = struct.pack("<5f", 1.0, 0.5, 0.25, 0.125, 0.0)
        self.meta = metadata("case:seq0:pos112", "a" * 64, vocab=5)

    def test_identical_bytes(self):
        values = validate_blob(self.data, self.meta, 5)
        result = pair(self.data, values, self.data, values)
        self.assertEqual(result["bitwise_equal_count"], 5)
        self.assertEqual(result["softmax_total_variation"], 0)

    def test_one_changed_value(self):
        other = struct.pack("<5f", 1.0, 0.5, 0.25, 0.125, 0.1)
        result = pair(self.data, validate_blob(self.data, self.meta, 5),
                      other, validate_blob(other, self.meta, 5))
        self.assertEqual(result["bitwise_equal_count"], 4)
        self.assertEqual(result["first_different_index"], 4)

    def test_signed_zero_is_bitwise_difference(self):
        other = struct.pack("<5f", 1.0, 0.5, 0.25, 0.125, -0.0)
        result = pair(self.data, validate_blob(self.data, self.meta, 5),
                      other, validate_blob(other, self.meta, 5))
        self.assertEqual(result["float_equal_count"], 5)
        self.assertEqual(result["bitwise_equal_count"], 4)
        self.assertEqual(result["signed_zero_byte_mismatch_count"], 1)

    def test_swapped_token_metadata(self):
        other = {**self.meta, "state_id": "other:seq0:pos112",
                 "token_ids_sha256": "b" * 64}
        with self.assertRaisesRegex(EvidenceError, "token IDs differ"):
            validate_records([(self.data, self.meta), (self.data, other)], 5)

    def test_wrong_shape_stride_and_truncated_bytes(self):
        for meta, data in (({**self.meta, "shape": [4]}, self.data),
                           ({**self.meta, "strides": [8]}, self.data),
                           (self.meta, self.data[:-4]),
                           ({**self.meta, "dtype": "f16le"}, self.data)):
            with self.subTest(meta=meta, length=len(data)):
                with self.assertRaises(EvidenceError):
                    validate_blob(data, meta, 5)

    def test_nan_and_missing_metadata(self):
        bad = struct.pack("<5f", 1, 0.5, math.nan, 0.125, 0)
        with self.assertRaisesRegex(EvidenceError, "non-finite"):
            validate_blob(bad, self.meta, 5)
        missing = dict(self.meta)
        del missing["sequence_id"]
        with self.assertRaisesRegex(EvidenceError, "metadata"):
            validate_blob(self.data, missing, 5)

    def test_duplicate_or_empty_state(self):
        with self.assertRaisesRegex(EvidenceError, "duplicate state"):
            validate_records([(self.data, self.meta), (self.data, self.meta)], 5)
        with self.assertRaisesRegex(EvidenceError, "empty row"):
            validate_records([], 5)

    def test_report_is_no_replace(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "report.json"
            write_new(output, {"status": "DIAGNOSTIC"})
            with self.assertRaises(FileExistsError):
                write_new(output, {"status": "OVERWRITTEN"})


if __name__ == "__main__":
    unittest.main()
