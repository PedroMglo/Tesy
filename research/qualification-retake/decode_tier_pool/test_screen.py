import unittest

from screen import Bank, changes, comparison, evaluate, repair


class PoolTests(unittest.TestCase):
    def test_warm_tie_uses_first_physical_slot_and_pins_late_rank(self):
        keys = [(0, e) for e in (9, 4, 7, 5, 1)]
        b = Bank(keys)
        ranks = [(0, e) for e in (2, 4, 9, 7)]
        self.assertEqual(b.serve(ranks, 0), [(0, 2)])
        self.assertEqual(b.slots, [*keys[:3], (0, 2), (0, 1)])
        self.assertEqual(b.age, [3, 2, 4, 1, 0])
        self.assertEqual(b.serve([(0, e) for e in (3, 4, 2, 7)], 4), [(0, 3)])
        self.assertEqual(b.slots[-1], (0, 3))

    def test_prefers_empty_and_layer_is_part_of_identity(self):
        b = Bank([(0, 1), (1, 1), None, None, None, None])
        self.assertEqual(b.serve([(1, e) for e in (2, 1, 3, 4)], 0), [(1, 2), (1, 3), (1, 4)])
        self.assertEqual(b.slots[:3], [(0, 1), (1, 1), (1, 2)])
        with self.assertRaises(ValueError):
            b.serve([(1, 1)] * 4, 4)
        with self.assertRaises(ValueError):
            Bank([(0, 1), (0, 1)])

    def test_cycle_and_missing_final_keys_are_distinct(self):
        a, b, c, d = ((1, x) for x in range(4))
        report = repair([b, a, c, None], [a, b, c, d])
        self.assertEqual(report[1], {"displaced": 2, "in_place": 1, "restore": 1})
        self.assertEqual(repair([a, b], [None, b])[1], {"in_place": 1})

    def test_same_schedule_and_operating_cut(self):
        # L1's empty slots can serve L0; neither tier starts with a free preloaded key.
        start = [None] * 1440
        groups = [
            (c, il, c, [4 * ((c - 1) % 11) + j for j in range(4)] if il == 0 else list(range(4)))
            for c in range(1, 33)
            for il in range(36)
        ]
        r = evaluate(start, start, groups, [0] * 1152)
        self.assertGreater(
            r["policies"]["local"]["total"]["misses"], r["policies"]["shared"]["total"]["misses"]
        )
        self.assertEqual(
            r["policies"]["local"]["tiers"]["CUDA"], r["policies"]["shared"]["tiers"]["CUDA"]
        )
        self.assertEqual(sum(r["groups_changed"]["local"].values()), 1152)
        self.assertTrue(comparison(85, 100)["passes"])
        self.assertFalse(comparison(86, 100)["passes"])
        self.assertEqual(
            changes([1, 0, 1, 0], [0, 1, 1, 0]),
            {"new_miss": 1, "eliminated_miss": 1, "both_miss": 1, "both_hit": 1},
        )
