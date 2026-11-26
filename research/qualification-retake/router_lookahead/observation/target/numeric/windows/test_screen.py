import unittest
from pathlib import Path
from runpy import run_path

S = run_path(str(Path(__file__).with_name("screen.py")))


class Windows(unittest.TestCase):
    def test_read_occupancy_transforms_both_edges(self):
        clock, occupied = S["available_clock"]([(15, 28), (10, 17), (30, 40)])
        self.assertEqual(occupied, 28)
        self.assertEqual([clock(t) for t in (8, 12, 25, 28, 29, 41)], [8, 10, 10, 10, 11, 13])
        s = [(1, 15, "prefill/CPU", [1], {1: (24, 29, 39)})]
        moved = S["retime"](s, clock)
        self.assertEqual(moved[0][1], 10)
        self.assertEqual(moved[0][4][1], (10, 11, 12))

    def test_fifo_carries_false_offers_across_target_types(self):
        sites = [(1, 0, "decode/CUDA", [8, 9], {}), (2, 1, "prefill/CPU", [10], {10: (2, 2, 2)})]

        def get(s):
            return S["W"]["evaluate"](s, 10**9, window=1)["global"]

        both, filtered = get(sites), get(sites[1:])
        self.assertEqual((both["accept_or_barrier_fifo"], both["accept_or_barrier_oracle"]), (0, 1))
        self.assertEqual(filtered["accept_or_barrier_fifo"], 1)

    def test_overlap_and_frequency_after_filter(self):
        s = [
            (1, 10, "prefill/CPU", [7], {7: (13, 14, 20)}),
            (2, 14, "prefill/CPU", [3], {3: (15, 15, 17)}),
        ]
        counts = S["W"]["evaluate"](s, 10**9, window=1)["sites_overlapping_previous_deadlines"]
        self.assertEqual(counts, {"reserve": 0, "accept_or_barrier": 0, "barrier": 1})
        ids, dropped = S["M"]["choose"]([[7, 5, 1, 2], [5, 7, 3, 1]], {1}, 2)
        self.assertEqual((ids, dropped), ([5, 7], 1))


if __name__ == "__main__":
    unittest.main()
