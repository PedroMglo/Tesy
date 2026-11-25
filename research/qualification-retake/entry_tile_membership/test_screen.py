import struct
import unittest

from screen import bytes_to_cut, choose, decode_prefix, geometry, project


def fake_prefix(case):
    sizes, graphs = geometry(case)
    out = bytearray(b"WRT1")
    start = 0
    for call, n in enumerate(sizes, 1):
        out.extend(b"C" + struct.pack("<HH", start, n))
        for cid, _, positions in graphs:
            if cid != call:
                continue
            width = len(positions)
            out.extend(b"U" + bytes([width]) + struct.pack("<" + "H" * width, *positions))
            for layer in range(35):
                out.extend(
                    b"R"
                    + bytes([layer, width])
                    + struct.pack("<H", 512)
                    + bytes([1, 2, 3, 4]) * width
                )
            if positions[-1] == start + n - 1:
                out.extend(
                    b"O"
                    + bytes([width - 1])
                    + b"R"
                    + bytes([35, 1])
                    + struct.pack("<H", 512)
                    + bytes([5, 6, 7, 8])
                )
            out.extend(b"E")
        out.extend(b"D")
        start += n
    return bytes(out)


class SealedTile(unittest.TestCase):
    def test_prefix_cut_stops_before_decode(self):
        for case in ("nominal153", "code153"):
            prefix = fake_prefix(case)
            sizes, plan = geometry(case)
            self.assertEqual(len(prefix), bytes_to_cut(sizes, len(plan)))

            class Guard:
                def __init__(self, data):
                    self.data = data
                    self.calls = 0

                def read(self, n):
                    self.calls += 1
                    if self.calls > 1 or n != len(self.data):
                        raise AssertionError("suffix exposed")
                    return self.data

            t = decode_prefix(Guard(prefix), case)
            self.assertEqual(len(t), 153 * 35 + 1)
            self.assertEqual(t[-1][1], 35)

    def test_recurrence_gap_and_membership_after_I(self):
        t = [
            (ub, 0, ub, (expert, 100, 101, 102))
            for ub, expert in ((1, 1), (3, 1), (4, 2), (5, 1), (5, 2), (5, 3), (5, 4))
        ]
        t.append((5, 35, 8, (4, 5, 6, 7)))
        entry = [set() for _ in range(36)]
        entry[0] = {3, 100, 101, 102}
        r = choose(t, entry)
        self.assertEqual(r["reappeared"], [[0, 1, 21]])
        self.assertEqual(r["last_tile"], [[0, 1, 21], [0, 2, 24], [0, 4, 16]])

    def test_recomputes_last_worker(self):
        r = project([(0, {1: 99, 2: 81}), (25, {3: 22})], {(0, 1), (25, 3), (25, 4)}, 420)
        self.assertEqual(r["required_read_us"], 81)
        self.assertEqual(r["tiers"]["CUDA"]["selected_never_demanded"], 1)
        self.assertEqual(r["max_read_scale"], (16_000_000 - 3 * 420) / (3 * 81))
