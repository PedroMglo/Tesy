import struct
import unittest

import screen


class Location(unittest.TestCase):
    def test_sign_high_byte_and_finite_distinction(self):
        key = ("swa", "K", 0, 189)
        left = bytes(1024)
        right = bytearray(1024)
        struct.pack_into("<HHH", right, 2, 0x8000, 1, 0x7C00)
        diff = screen.compare((left, {key: 0}), (right, {key: 0}))
        self.assertEqual(diff["first_file"]["byte_offset"], 3)
        self.assertEqual(diff["totals"]["differing_words"], 3)
        self.assertEqual(diff["totals"]["zero_sign"], 1)
        self.assertEqual(diff["totals"]["nonfinite_in_pair"], 1)
        self.assertEqual(diff["totals"]["unequal_finite"], 1)

    def test_metadata_and_payload_boundaries(self):
        header = struct.pack("<II", 0xAF143CD8, 0)
        bank = struct.pack("<II", 1, 128)
        cells = b"".join(struct.pack("<iIi", pos, 1, 0) for pos in range(128))
        config = struct.pack("<II", 0, 1)
        tensor = struct.pack("<iQ", 1, 1024) + bytes(128 * 1024)
        base = bank + cells + config + tensor * 2
        blob = header + base * 2
        rows, _ = screen.parse(blob, 128, [[1], [0]])
        self.assertEqual(rows["swa", "V", 0, 127], len(blob) - 1024)
        for bad in (blob[:-1], blob + b"x", blob[:16] + struct.pack("<I", 1) + blob[20:]):
            with self.assertRaises((ValueError, struct.error)):
                screen.parse(bad, 128, [[1], [0]])
