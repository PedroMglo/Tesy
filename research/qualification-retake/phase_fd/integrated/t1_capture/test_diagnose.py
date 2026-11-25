import importlib.util
import unittest
from pathlib import Path

sp = importlib.util.spec_from_file_location(
    "pfj1_t1_diagnostics", Path(__file__).with_name("diagnose.py")
)
m = importlib.util.module_from_spec(sp)
sp.loader.exec_module(m)


class FirstDifference(unittest.TestCase):
    def test_singular_slot_order_within_site(self):
        a = (10, 1, 1, 3, 0, 30, 6, 24, 0)
        b = (10, 1, 1, 3, 0, 41, 2, 25, 0)
        change = m.comparison([a, b], [b, a])
        self.assertFalse(change["ordered_equal"])
        self.assertTrue(change["multiset_equal"])
        self.assertEqual(change["sites"]["differing_multisets"], 0)
        self.assertEqual(change["first"]["fields"], ["expert", "slot", "generation"])
        self.assertNotIn("expert", change["first"]["current"])
        self.assertNotIn("expert", m.comparison([a[:6]], [b[:6]])["first"]["current"])
        self.assertEqual(m.comparison([a], [])["first"]["fields"], ["length"])

    def test_rank_swap_and_last_output_absolute_position(self):
        a = (27, 2, 5, 35, 0, 0x01020304, 0)
        b = (*a[:5], 0x01020403, 0)
        v = m.rank_comparison([a], [b], {(2, 5): (2177, 2196)})
        self.assertEqual(v["changed_rank_sets"], 0)
        self.assertEqual(v["first"]["absolute_position"], 2196)
        self.assertEqual(v["first"]["changed_rank_indices"], [0, 1])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            m.rank_comparison([a, a], [b], {(2, 5): (2177, 2196)})

    def test_sequence_length_and_interclass_order(self):
        a = (11, 3, 1, 17, -1, 5, 13, 80, 50)
        b = (12, 3, 1, 17, -1, 5, 13, 80, 0)
        r = m.comparison([a, b], [b, a])
        self.assertEqual(r["sites"]["differing_sequences"], 0)
        self.assertTrue(r["multiset_equal"])
        self.assertEqual(r["first"]["current"]["kind"], 11)
        self.assertEqual(r["first"]["prior"]["kind"], 12)


if __name__ == "__main__":
    unittest.main()
