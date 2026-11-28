import unittest
from pathlib import Path
from runpy import run_path

P = run_path(Path(__file__).with_name("tile_cost.py"))


class TileTests(unittest.TestCase):
    def test_no_read_is_discounted_twice(self):
        f = P["paid_job"]
        self.assertEqual(f(100, 8, 40, False, False, False), (68, 40))
        self.assertEqual(f(100, 8, 40, False, True, True), (8, 0))
        self.assertEqual(f(100, 8, 0, True, False, True), (0, 0))
        with self.assertRaises(ValueError):
            f(100, 8, 0, True, True, False)

    def test_overlap_cannot_escape_the_shared_worker_or_link_budget(self):
        stages = [(7, 6), (7, 6)]
        self.assertEqual(P["tile_clocks"](stages, 0, 0), (26, 20))
        self.assertEqual(P["tile_clocks"](stages, 22, 23), (26, 23))
        self.assertEqual(P["tile_clocks"](stages, 30, 23), (30, 30))


if __name__ == "__main__":
    unittest.main()
