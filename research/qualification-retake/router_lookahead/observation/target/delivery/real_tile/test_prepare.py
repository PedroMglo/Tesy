"""Independent negative controls for strided golds, binding epochs and source admission."""

import struct
import tempfile
import unittest
from pathlib import Path
from runpy import run_path

M = run_path(str(Path(__file__).with_name("prepare.py")))


class PrepareTest(unittest.TestCase):
    def test_real_stride_discards_only_padding_and_rejects_wrong_pitch(self):
        raw = bytearray([0xDA]) * (31 * 512 + 16)
        expected = []
        for i in range(32):
            quartet = [i, i + 1, i + 2, i + 3]
            expected.extend(quartet)
            struct.pack_into("<4i", raw, i * 512, *quartet)
        row = dict(
            name="ffn_moe_topk",
            ne="4,32,1,1",
            nb="4,512,16384,16384",
            type="i32",
            bytes=len(raw),
            chunk="0",
            first_abs="0",
            state_tokens="32",
        )
        _, dense = M["tensor"](row, raw)
        self.assertEqual(M["numbers"](dense, "i"), expected)
        with self.assertRaisesRegex(ValueError, "descriptor"):
            M["tensor"](dict(row, nb="4,16,512,512"), raw)

    def test_active_binding_inactive_parking_and_archive_integrity(self):
        logical = [43, 56, 43, 0]
        physical = [3, 4, 3, -1]
        one = 0x3F800000
        masks = [one, 0, one, 0]
        self.assertEqual(
            M["wave_generations"](logical, physical, masks, {43: (3, 7)}), [7, 0, 7, 0]
        )
        with self.assertRaisesRegex(ValueError, "active C270/PFJ"):
            M["wave_generations"](logical, physical, masks, {43: (4, 7)})
        with self.assertRaisesRegex(ValueError, "incomplete active"):
            M["wave_generations"](logical, physical, masks, {43: (3, 7), 56: (4, 2)})
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "metadata"
            file.write_bytes(b"wrong")
            budget = M["Inputs"](Path(root))
            with self.assertRaisesRegex(ValueError, "digest"):
                budget.sealed(file, M["sha"](b"right"))
            with self.assertRaisesRegex(ValueError, "budget"):
                budget.charge(M["CAP"], "pack_bias")


if __name__ == "__main__":
    unittest.main()
