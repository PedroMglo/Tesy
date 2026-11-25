import unittest
from pathlib import Path
from runpy import run_path

m = run_path(Path(__file__).with_name("screen.py"))


class MarginalCosts(unittest.TestCase):
    def test_retained_set_can_change_the_critical_worker(self):
        self.assertEqual(m["remove_read"]([(8, 4, True), (2, 9, False)]), 1)
        self.assertEqual(m["remove_read"]([(8, 4, True), (13, 2, False)]), 0)
        self.assertEqual(m["remove_read"]([(1, 9, True)]), 1)

    def test_concurrent_short_jobs_need_not_move_the_last_barrier(self):
        self.assertEqual(m["fifo"]([10, 2, 4, 6]), 10)
        self.assertEqual(m["fifo"]([10, 4, 6]), 10)
        self.assertEqual(m["fifo"]([10, 4, 6, 1, 15]), 16)

    def test_rank_position_and_generation_distinguish_repeated_expert(self):
        site = dict(call=2, tile=1, layer=5, wave=0)
        job = dict(ordinal=3, expert=22, slot=15, generation=6)
        self.assertNotEqual(m["key"](site, job), m["key"](site, dict(job, generation=7)))


if __name__ == "__main__":
    unittest.main()
