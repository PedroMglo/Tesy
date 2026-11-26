import unittest
from pathlib import Path
from runpy import run_path

s = run_path(Path(__file__).with_name("screen.py"))
Row = s["fd"].Row


def row(k, ns, **kw):
    d = dict.fromkeys(Row._fields, 0) | dict(kind=k, ns=ns, wave=0, a=1, call=1, tile=1)
    return Row(**(d | kw))


def pair():
    return [row(9, 90), row(23, 100), row(9, 150, layer=1), row(23, 175, layer=1)]


class TestGaps(unittest.TestCase):
    def grade(self, rows):
        return s["census"](rows, 1)[0][1, 1]

    def test_drained_versus_crossing(self):
        self.assertEqual(self.grade(pair())["drained_ns"], 50)
        # A worker that claimed data before the first remap and publishes mid-interval.
        rows = [row(5, 10, b=1)] + pair()[:2] + [row(17, 120)] + pair()[2:]
        self.assertEqual(self.grade(rows)["inflight_or_new_work"], 1)
        # A queued stale job is outstanding even when no slot currently loads.
        self.assertEqual(self.grade([row(6, 10, b=1)] + pair())["drained"], 0)
        # Detect overlap by duration even if the completion record is appended later.
        self.assertEqual(self.grade(pair() + [row(16, 200, begin=140)])["spanning_service"], 1)

    def test_geometry_and_zero_length(self):
        p = pair()
        for field in ("call", "tile"):
            changed = p[:2] + [r._replace(**{field: 2}) for r in p[2:]]
            self.assertEqual(self.grade(changed)["neighbor_transitions"], 0)
        self.assertEqual(self.grade(p[:2] + [r._replace(a=0) for r in p[2:]])["no_next_routes"], 1)
        self.assertEqual(self.grade(p[:2] + [p[2]._replace(ns=100), p[3]])["drained_ns"], 0)
        with self.assertRaisesRegex(ValueError, "clock"):
            self.grade(p[:2] + [p[2]._replace(ns=99), p[3]])

    def test_allowance(self):
        r = s["price"](4_000_000_000, 4_500_000_000, 200_000_000)
        self.assertAlmostEqual(r["retaining_all_gaps_minimum_GBs"], 5)
        self.assertFalse(r["all_gaps_fit_at_4p5_GBs"])
        self.assertAlmostEqual(r["max_observed_gap_fraction"], 5 / 9)


if __name__ == "__main__":
    unittest.main()
