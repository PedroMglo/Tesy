import unittest
from pathlib import Path
from runpy import run_path

P = run_path(Path(__file__).with_name("tile_cost.py"))
L = run_path(Path(__file__).with_name("tile_lanes.py"))


class TileTests(unittest.TestCase):
    def test_cut_counts_global_capacity_and_each_single_reader(self):
        five = [(i, 10, 0, 10) for i in range(5)]
        cut = L["max_service"](five)
        self.assertEqual(cut["deficit_worker_ns"], 10)
        self.assertEqual(cut["cut_capacity_worker_ns"], 40)
        self.assertEqual(L["max_service"]([(1, 11, 1, 10)])["deficit_worker_ns"], 2)
        self.assertTrue(L["max_service"](five[:4])["feasible"])

    def test_deadline_miss_in_the_witness_can_still_pass_flow(self):
        jobs = [(i, 5, 0, 20) for i in range(4)] + [(4, 2, 1, 3)]
        self.assertTrue(L["max_service"](jobs)["feasible"])
        self.assertEqual(L["dispatch"](jobs)["first_miss"], [3, 4, 4])
        self.assertTrue(L["dispatch"](jobs[:3] + jobs[4:])["passed"])

    def test_two_tile_limit_restricts_earliest_front_and_latest_tail(self):
        early, suffix, _, limit = L["stage_dag"]([[1, 9]] * 3)
        self.assertEqual(early, [0, 1, 1, 10, 10, 19])
        self.assertEqual(suffix[1], 18)
        self.assertEqual(limit, 28)

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
