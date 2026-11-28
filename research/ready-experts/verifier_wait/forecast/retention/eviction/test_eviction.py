"""Check router group conservation and auxiliary pins at the physical slot boundary."""

import unittest
from pathlib import Path
from runpy import run_path

D = Path(__file__).resolve().parent
R = run_path(D / "retention.py")
P = R["P"]
Event = R["Event"]


def row(i, layer, expert, lost=None, tile=1, call=2):
    return Event(
        i,
        (call, tile, layer),
        (layer, expert),
        i,
        1,
        True,
        lost,
        "primary_CPU" if lost else None,
        i if lost else None,
    )


class BoundedRetention(unittest.TestCase):
    def test_pinned_until_site_end_including_other_reservations(self):
        rows = [
            row(0, 0, 0, (1, 8)),
            row(1, 0, 1, (1, 9)),
            row(2, 1, 8, (2, 7)),
            row(3, 1, 9, (2, 6)),
            row(4, 2, 6),
            row(5, 2, 7),
        ]
        intervals = R["demand_intervals"](rows)
        self.assertEqual(len(intervals), 4)
        hits, captures = R["causal"](rows, None, "recency")
        self.assertTrue(hits.keys() <= intervals.keys())
        # At event 2 expert 8 is pinned and 9 can be expelled. At event 3
        # the pending eviction cannot evict the pinned 8.
        self.assertEqual({iv.expert for iv in hits}, {8, 6})
        self.assertEqual(sum(captures.values()), 4)

    def test_external_return_clears_the_last_source(self):
        rows = [row(0, 0, 1, (0, 7), call=1), row(1, 0, 7)]
        self.assertFalse(R["demand_intervals"](rows))
        self.assertFalse(R["causal"](rows, None, "recency")[0])

    def test_score_never_sees_another_return_or_a_completed_layer(self):
        fake = [[[[99], [99]]], [[[2], [3]], [[7], [11]]]]
        self.assertEqual(R["score"](fake, (2, 1, 0), (0, 0)), 7)
        self.assertEqual(R["score"](fake, (2, 1, 0), (1, 0)), 14)
        self.assertEqual(R["score"](fake, (1, 1, 1), (1, 0)), 0)

    def test_wrong_group_rejected_before_grade(self):
        counts = [[34] + [0] * 35 + [692] + [0] * 179 for _ in range(2)]
        lines = ["fd 3", "parity 726 7"]
        for arm, mode in enumerate((0, 1, 1, 0), 1):
            for i, n in enumerate(counts[mode], 1):
                lines.append(f"step {arm} {mode} {i} {n} {(n + 3) // 4} {int(n > 0)} 3")
        lines.append("drained")
        plan = dict(pack_stat=[3], unique=726, counts=counts)
        self.assertEqual(P["parse"](lines, plan)["component_hashes"], 2178)
        lines[3] = "step 1 0 2 1 1 1 3"
        with self.assertRaises(ValueError):
            P["parse"](lines, plan)


if __name__ == "__main__":
    unittest.main()
