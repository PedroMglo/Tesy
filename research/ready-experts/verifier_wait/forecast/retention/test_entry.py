"""Classify the four disjoint supplies and invalidate duplicate entry owners."""

import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

M = run_path(Path(__file__).with_name("entry.py"))


class Entry(unittest.TestCase):
    def test_disjoint_census(self):
        e = {1, 3}
        s = {2, 3}
        self.assertEqual(
            [M["classify"](e, s, i) for i in range(4)],
            ["first_absent", "entry_only", "supplied_only", "both"],
        )

    def test_invalid_owners_rejected(self):
        p = {(0, 0): (7, 2), (25, 0): (9, 4)}
        a, b = SimpleNamespace(held={(0, 9): 0}), SimpleNamespace(held={(25, 7): 0})
        self.assertEqual(M["entry_state"](p, [a, b])[(25, 9)], "primary_back")
        a.held[(0, 7)] = 1
        with self.assertRaises(ValueError):
            M["entry_state"](p, [a, b])


if __name__ == "__main__":
    unittest.main()
