"""Portably exercise the complete interval and generation tests using no model or captures."""

import unittest
from pathlib import Path
from runpy import run_path

s = run_path(Path(__file__).with_name("screen.py"))
SIZE, COUNT = s["ROLE"], s["SLOTS"]


class AddressTest(unittest.TestCase):
    def test_all_possible_cold_slots_keep_three_other_ranks(self):
        for cold in range(COUNT):
            slots = [(cold + k) % COUNT for k in range(4)]
            result = s["remap_proof"]([[120 - i, j, 1 + i] for i, j in enumerate(slots)])
            self.assertTrue(all(r["original_affine"] for r in result["role_results"]))
            self.assertTrue(
                all(not r["one_host_three_retained_affine"] for r in result["role_results"])
            )

    def test_whole_arena_rebase_and_one_changed_operand(self):
        slots = [4, 5, 6, 7]
        for base in (10000, 50000):
            starts = [base + i * SIZE for i in slots]
            self.assertTrue(s["single_base"](slots, starts, SIZE))
            starts[0] += 17
            self.assertFalse(s["single_base"](slots, starts, SIZE))
        with self.assertRaises(ValueError):
            s["single_base"](slots, [0] * 4, SIZE + 1)

    def test_guarded_backing(self):
        for offset in (0, SIZE, 2 * SIZE):
            r = [4, 9, 9, offset, offset + SIZE]
            self.assertEqual(s["tagged_interval"](r, SIZE), (offset, offset + SIZE))
            for i, bad in ((0, 40), (2, 8), (4, offset + SIZE - 1)):
                broken = r.copy()
                broken[i] = bad
                with self.assertRaises(ValueError):
                    s["tagged_interval"](broken, SIZE)

    def test_granularity_independent_of_base_residue(self):
        # For an interior slot, even giving either endpoint perfect alignment cannot save both.
        for gran in (4096, 65536):
            for slot in range(1, 39):
                left = (-slot * SIZE) % gran
                right = (-(slot + 1) * SIZE) % gran
                self.assertNotEqual(left, right)
                self.assertNotEqual(s["pages"](slot, gran, left), (0, 0))
                self.assertNotEqual(s["pages"](slot, gran, right), (0, 0))


if __name__ == "__main__":
    unittest.main()
