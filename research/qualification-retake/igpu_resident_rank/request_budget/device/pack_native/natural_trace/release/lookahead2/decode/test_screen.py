import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

S = run_path(str(Path(__file__).with_name("screen.py")))


class SplitPrice(unittest.TestCase):
    def test_tail_only_changes_decode(self):
        v = S["budget"](5_000_000_000, 4_000_000_000, [20, 30, 17], [8, 10, 7])
        self.assertEqual(v["first_floor_ns"], 5_000_000_000 - 12 - 20)
        self.assertEqual(v["decode_floor_ns"], 4_000_000_000 - 20 - 10)
        self.assertEqual(
            v["shared_extra_ceiling_ns"], min(v["first_margin_ns"], v["decode_margin_ns"])
        )
        self.assertEqual(
            S["budget"](11_000_000_000, 2_000_000_000, [0] * 3, [0] * 3)["joint"],
            "NO_GO_FIXED_SCENARIO",
        )

    def test_four_workers_and_shared_clock(self):
        # Five serial job chains of 4 ns: no four workers can supply 20 worker-ns in 4 ns.
        self.assertEqual(S["REL"]["four_lanes"]([4] * 5), 5)
        # Two 8 B jobs with one common 10 ns window at 1 B/ns, including both tiers.
        early, net, both = S["resources"](16, [(0, 10, 8)] * 2, 10**9, 9)
        self.assertEqual((early, net, both), (10 * 10**9, 6, 9))
        shrink = S["L"]["contracted"]([(0, 10)])
        self.assertEqual(
            S["resources"](16, [(shrink(0), shrink(10), 8)] * 2, 10**9, 9), (0, 16, 16)
        )

    def test_uncertain_first_piece(self):
        def w(call, a, b):
            return SimpleNamespace(site=(call,), start=a, end=b)

        S["assert_cut"]([w(46, 0, 10), w(47, 15, 20)], 10, 15)
        for waves in ([w(46, 0, 11)], [w(47, 14, 20)]):
            with self.assertRaisesRegex(ValueError, "INCONCLUSIVE"):
                S["assert_cut"](waves, 10, 15)

    def test_projection_cannot_use_previous_token_for_layer_zero(self):
        self.assertEqual(
            S["L"]["windows"](
                (3, 1, 0, -1), ({(3, 1, 0): 90}, {}, {}, {}, []), 1, "earliest_outer"
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
