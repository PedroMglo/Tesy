import unittest
from itertools import combinations
from pathlib import Path
from runpy import run_path

S = run_path(str(Path(__file__).with_name("screen.py")))


class FullDelivery(unittest.TestCase):
    def test_pfj_enqueues(self):
        S["verify_reason"](0, -1, -1)
        S["verify_reason"](2, 0, 1)
        for args in [(1, 0, 1), (2, 0, 0), (0, 0, 1)]:
            with self.assertRaises(ValueError):
                S["verify_reason"](*args)

    def test_preload_sets_can_hide_until_the_demand(self):
        self.assertEqual(S["set_floor"]([(5, 15, 8)]), 0)
        self.assertEqual(S["set_floor"]([(5, 15, 18)]), 8)
        self.assertEqual(S["set_floor"]([(5, 5, 4)] * 5), 5)
        self.assertEqual(S["set_floor"]([(5, 5, 4), (5, 15, 8), (15, 15, 3)]), 7)

    def test_four_tags_are_private_and_bank_replaces_own(self):
        store = S["Store"]("worker4", {11})
        self.assertEqual(store.dispatch(8, 0), "pack")
        store.read_done(8, 0, "CPU")
        self.assertEqual(store.dispatch(8, 0), "staging")
        self.assertEqual(store.dispatch(8, 1), "pack")
        self.assertEqual(store.dispatch(11, 0), "bank")
        self.assertEqual(store.dispatch(8, 0), "pack")
        self.assertFalse(store.available)

    def test_eviction_capture_and_carry(self):
        for mode, after_victim in (
            ("retain_evictions_and_reads", "staging"),
            ("retain_reads", "pack"),
        ):
            store = S["Store"](mode, {22})
            store.evict(2, "CUDA0")
            self.assertEqual(store.dispatch(2, 3), after_victim)
            self.assertEqual(store.dispatch(12, 1), "pack")
            store.read_done(12, 1, "CPU")
            self.assertEqual(store.dispatch(12, 3), "staging")
            store.evict(22, "CUDA0")
            self.assertNotIn(22, store.available)

    def test_bound_for_distinct_identity_licences(self):
        size = S["size"]
        g = [(0, 3), (1, 4), (2, 4), (2, 8), (0, 9), (3, 10)]
        for n in (0, 1, 2, 4):
            jobs = S["read_tasks"](g, 0, 3, n)
            optimum = max(
                S["L"]["early_capacity"](
                    [(0 if k in bank else 3, d, size) for k, d in g], size, scale=1
                )
                for bank in combinations(range(4), n)
            )
            self.assertGreaterEqual(S["L"]["early_capacity"](jobs, size, scale=1), optimum)
        self.assertEqual(S["read_tasks"]([(0, 10)], 4, 4, None), [(4, 10, size)])
        with self.assertRaises(ValueError):
            S["read_tasks"]([(0, 2)], 0, 3, None)


if __name__ == "__main__":
    unittest.main()
