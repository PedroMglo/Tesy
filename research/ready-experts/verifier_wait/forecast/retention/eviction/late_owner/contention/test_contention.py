"""Half-open service intervals, occupancy, and the boundary of a causal quartet."""

import unittest
from pathlib import Path
from runpy import run_path

F = run_path(Path(__file__).with_name("frontier.py"))
DEVICE = run_path(Path(__file__).with_name("device.py"))
VICTIMS = run_path(Path(__file__).with_name("victims.py"))


def job(i, start, end, region=(2, 5, 14), layer=14):
    return [[layer, i, 0, i], list(region), 0, i % 4, 0, start, end]


class InterferenceTests(unittest.TestCase):
    def test_clipped_union_never_counts_two_hits_twice(self):
        merged = F["intervals"]([(2, 5), (8, 11), (3, 6), (6, 6)])
        self.assertEqual(merged, [[2, 6], [8, 11]])
        self.assertEqual(F["overlap"](3, 10, merged), 5)
        self.assertEqual(F["overlap"](6, 8, merged), 0)

    def test_four_jobs_share_positive_time_and_one_hit(self):
        rows = [job(i, i, 8) for i in range(4)]
        self.assertEqual(F["quartets"](rows, {3}), {(3, 1, 2, 4)})
        self.assertFalse(F["quartets"](rows, {2, 3}))
        rows[0][6] = 3
        self.assertFalse(F["quartets"](rows, {3}))

    def test_another_tile_and_cuda_do_not_select(self):
        rows = [job(i, i, 9) for i in range(4)]
        rows[0][1] = [2, 4, 14]
        self.assertFalse(F["quartets"](rows, {3}))
        rows = [job(i, i, 9, region=(2, 5, 26), layer=26) for i in range(4)]
        self.assertFalse(F["quartets"](rows, {3}))

    def test_grant_conserves_other_prices(self):
        arm = {"regions": [[2, [[3, 4, [[1, 9, 2], [2, 7, 4]]]], [], 0]]}
        amended = F["adjusted"](arm, {1: 5}, {2})
        self.assertEqual(amended["regions"][0][1][0][2], [[1, 4, 2], [2, 7, 0]])
        self.assertEqual(arm["regions"][0][1][0][2], [[1, 9, 2], [2, 7, 4]])
        with self.assertRaises((ValueError, RuntimeError, AssertionError)):
            F["adjusted"](arm, {2: 8})


class DeviceTests(unittest.TestCase):
    def fixture(self, reverse, observer):
        spec = dict(labels=["example"], pack_stat=[1, 2, 3, 4, 5], expected_records=229)
        lines = ["fd 1 2 3 4 5"]
        for stage, order, p, h, t in DEVICE["schedule"]():
            base = 100 + (reverse if order == 1 else -10) * h + observer * t
            times = [2, 20] * 4 if t else [0] * 8
            data = (0, stage, order, p, h, t, base, base + 10, base + 20, *times)
            lines.append("row " + " ".join(map(str, data)))
        lines.append("drained 61 61 61 46 183 183 183 183")
        return lines, spec

    def test_pair_signs_and_observer_are_independent(self):
        for reverse, observer, decision, neutral in (
            (-5, 0, "GO_LOCAL", "PASS"),
            (5, 0, "INCONCLUSIVE", "PASS"),
            (-5, 4, "GO_LOCAL", "NOT_NEUTRAL"),
        ):
            result = DEVICE["parse"](*self.fixture(reverse, observer))["groups"]["example"]
            self.assertEqual((result["decision"], result["neutrality"]), (decision, neutral))

    def test_short_read_wrong_destination_and_off_timestamps_fail(self):
        lines, spec = self.fixture(-5, 0)
        for index, changed in (
            (-1, lines[-1].replace("46", "45")),
            (-1, lines[-1].replace("183", "180")),
            (1, lines[1][:-1] + "2"),
            (1, lines[2]),
        ):
            edited = lines.copy()
            edited[index] = changed
            with self.assertRaises(ValueError):
                DEVICE["parse"](edited, spec)


class VictimTests(unittest.TestCase):
    def test_exact_four_and_mixed_are_different(self):
        rows = [job(0, 1, 6), job(1, 2, 7), job(2, 3, 8), job(3, 4, 9), job(4, 9, 12)]
        sets, work = VICTIMS["eligible"](rows, {1, 5})
        self.assertEqual(sets["clipped"], {2: 2, 3: 2, 4: 2})
        self.assertEqual(sets["whole_quartet"], {2: 5, 3: 5, 4: 5})
        self.assertEqual(work["any_mixed_wall_ns"], 4)
        rows[3][1] = [2, 4, 14]
        sets, work = VICTIMS["eligible"](rows, {1, 5})
        self.assertFalse(sets["clipped"])
        self.assertEqual(sets["any_peer"], {2: 5, 3: 5, 4: 5})

    def test_break_even_requires_both_clocks(self):
        def first_and_decode(ppm):
            return {
                "granted_first_ns": 10**10 + 172 - ppm,
                "decode": VICTIMS["C"]["B"]["DECODE_LIMIT"] + 187 - ppm,
            }

        result = VICTIMS["line"](first_and_decode)
        self.assertEqual((result["min_reduction_ppm"], result["preceding_margin_ns"]), (187, -1))


if __name__ == "__main__":
    unittest.main()
