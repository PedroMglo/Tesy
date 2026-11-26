import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import screen  # noqa: E402


def synthetic(transposed):
    data = bytearray(struct.pack("<Ii", screen.MAGIC, 0))
    for il in (1, 0):
        cells = [2, 0, 1] if il == 1 else [2, 1]
        data.extend(struct.pack("<II", 1, len(cells)))
        for p in cells:
            data.extend(struct.pack("<iIi", p, 1, 0))
        data.extend(struct.pack("<II", int(transposed), 1))
        for role in (0, 1):

            def values(pos, j, il=il, role=role):
                return 100 * il + 35 * role + pos * 3 + j

            if role and transposed:
                data.extend(struct.pack("<iII", 1, 2, 3))
                for j in range(3):
                    for p in cells:
                        data.extend(struct.pack("<H", values(p, j)))
            else:
                data.extend(struct.pack("<iQ", 1, 6))
                for p in cells:
                    data.extend(struct.pack("<3H", *(values(p, j) for j in range(3))))
    return data


class LayoutTests(unittest.TestCase):
    def test_transposed_and_permuted(self):
        def parse(b):
            return screen.parse(b, 3, ((1,), (0,)), 2, 3)[0]

        ref = parse(synthetic(False))
        cand = parse(synthetic(True))
        self.assertEqual(ref, cand)
        self.assertEqual(struct.unpack("<3H", ref[1, "V", 2]), (141, 142, 143))
        cand[0, "K", 2] = struct.pack("<3H", 6, 0x8007, 8)
        c = screen.contrast(ref, cand, 3)
        self.assertEqual(c["changed_words"], 1)
        self.assertEqual((c["first"][0]["role"], c["first"][0]["first_index"]), ("K", 1))
        cand[1, "K", 0] = struct.pack("<3H", 0x8000, 101, 102)
        ref[1, "K", 0] = struct.pack("<3H", 0x0000, 101, 102)
        self.assertEqual(screen.contrast(ref, cand, 3)["changed_words"], 2)

    def test_malformed_and_trailing(self):
        for tag in ("magic", "trailing", "truncated", "position", "type", "pitch"):
            b = synthetic(False)
            if tag == "magic":
                b[0] ^= 1
            if tag == "trailing":
                b += b"x"
            if tag == "truncated":
                b = b[:-1]
            if tag == "position":
                b[16:20] = struct.pack("<i", 0)
            if tag == "type":
                b[60:64] = struct.pack("<i", 4)
            if tag == "pitch":
                b[64:72] = struct.pack("<Q", 8)
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                screen.parse(b, 3, ((1,), (0,)), 2, 3)


if __name__ == "__main__":
    unittest.main()
