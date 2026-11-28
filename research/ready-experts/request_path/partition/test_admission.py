"""Focused invariants for bypass, full-wave hits and counter aging."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import admission as a  # noqa: E402
import policy as p  # noqa: E402


def wave(*keys):
    return p.Wave(1, 1, 0, 0, keys)


class AdmissionTests(unittest.TestCase):
    def test_bypass_is_still_a_full_read(self):
        obj = a.Directory("filter_lru", [0, 1], capacity=2)
        obj.count[0] = 5
        missing, stats = obj.serve(wave(2))
        self.assertEqual((missing, stats["reads"], stats["bypasses"]), ((2,), 1, 1))
        self.assertEqual(list(obj.bank), [0, 1])

    def test_minimum_can_remove_a_colder_recent_member(self):
        obj = a.Directory("filter_min", [0, 1], capacity=2)
        obj.count[:3] = [8, 0, 1]
        obj.serve(wave(2))
        self.assertEqual(list(obj.bank), [0, 2])

    def test_full_wave_keeps_its_entry_hits(self):
        obj = a.Directory("lru", [0, 1], capacity=2)
        missing, totals = obj.serve(wave(2, 0))
        self.assertEqual((missing, totals["reads"]), ((2,), 1))
        self.assertEqual(list(obj.bank), [2, 0])

    def test_aging_and_state_roundtrip(self):
        obj = a.Directory("filter_lru")
        obj.sample = 12119
        obj.count[0] = 7
        _, totals = obj.serve(wave(0))
        self.assertEqual((totals["resets"], obj.count[0], obj.sample), (1, 4, 6060))
        self.assertEqual(a.Directory.reopen("filter_lru", obj.freeze()).freeze(), obj.freeze())


if __name__ == "__main__":
    unittest.main()
