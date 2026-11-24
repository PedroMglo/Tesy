"""Small fault and interval checks for the preregistered WAIT projection."""

import unittest

from critical import commit_bounds, direct_window, selection_keys


class PublicationOrder(unittest.TestCase):
    def test_unlocked_timestamp_does_not_decide_publication_order(self):
        k1, k2 = (0, 8, 10, 1), (0, 9, 12, 3)
        rows = [dict(seq=i, kind=kind, mono_us=t, layer=k[0],
                     expert=k[1], slot=k[2], generation=k[3])
                for i, (kind, t, k) in enumerate([
                    ("WAIT_BEGIN", 50, k1), ("LOAD_END", 78, k1),
                    ("DEQUEUE", 81, k2), ("LOAD_END", 75, k2),
                    ("WAIT_END", 90, k2),
                ])]
        pub = commit_bounds(rows)
        self.assertEqual(pub[k1], (1, 78, 81))
        self.assertEqual(pub[k2], (3, 81, 90))
        self.assertEqual(direct_window(50, 90, [k1, k2], {k1}, pub), (0, 0))
        self.assertEqual(direct_window(50, 90, [k1, k2], {k2}, pub), (0, 13))
        self.assertEqual(direct_window(50, 90, [k1, k2], {k1, k2}, pub), (39, 41))

    def test_subset_aliases_reference_the_same_generation(self):
        events = [dict(seq=91, kind="LOAD_BEGIN", layer=2, expert=35, slot=6, generation=7)]
        expected = {(2, 35, 6, 7)}
        for sample in ([91], [[2, 6, 7]], [[2, 35, 6, 7]]):
            self.assertEqual(selection_keys(events, sample), expected)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            selection_keys(events, [91, [2, 6, 7]])
        with self.assertRaisesRegex(ValueError, "unknown"):
            selection_keys(events, [92])
