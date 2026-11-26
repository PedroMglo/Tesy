import unittest

from screen import compare, counts, replay, wave_stream


class Screen(unittest.TestCase):
    def test_decision_requires_total_repair_and_both_phase_protections(self):
        control = counts(40, 40, 20)
        self.assertTrue(compare(counts(40, 40, 10), control)["pass"])
        out = compare(counts(36, 36, 19), control)
        self.assertFalse(out["pass"])
        self.assertEqual(out["additional_loads_to_remove_for_10pct"], 1)
        self.assertFalse(compare(counts(41, 25, 20), control)["pass"])
        self.assertFalse(compare(counts(25, 41, 20), control)["pass"])
        self.assertEqual(compare(counts(1, 1, 0), counts(1, 1, 0))["allowed_total"], 1)

    def test_exact_start_preserved_and_F_charge(self):
        initial = [list(range(40)) for _ in range(36)]
        target = [set(slots) for slots in initial]
        work = [
            ("increment", 24, [40, 1, 40]),
            ("increment", 24, []),
            ("decode", 24, [41, 40]),
            ("decode", 25, [1, 2, 3, 4]),
        ]
        sims, differences = replay(initial, target, work)
        self.assertEqual(initial[24], list(range(40)))
        for r in sims.values():
            self.assertEqual(r["loads_by_tier"]["CUDA0"], counts(0, 0, 0))
            self.assertEqual(r["loads_by_tier"]["CPU"], counts(1, 1, 2))
            self.assertEqual(r["phases"]["increment"]["CPU"]["parking_only_waves"], 1)
            self.assertEqual(r["phases"]["increment"]["CPU"]["rank_uses"], 3)
            self.assertEqual(r["phases"]["increment"]["CPU"]["distinct_demands"], 2)
            gaps = sorted(target[24].difference(r["F_slots"][24]))
            self.assertEqual(r["missing_R0_F_by_layer"][24], gaps)
        self.assertEqual(differences["increment"]["CPU"]["compared_waves"], 1)

    def test_uninitialized_slots_and_first_use_order(self):
        initial = [[-1] * 40 for _ in range(36)]
        target = [set() for _ in range(36)]
        target[5] = {6, 7}
        rows = [
            (8, 0, 5, 0, (10, 11, 12, 13)),
            (9, 0, 5, 1, (9, 5, 6, 7)),
            (10, 1, 5, 2, (7, 6, 5, 9)),
        ]
        work = list(wave_stream(rows))
        self.assertEqual(work, [("increment", 5, [9, 5, 6, 7]), ("decode", 5, [7, 6, 5, 9])])
        policies, _ = replay(initial, target, work)
        for sim in policies.values():
            self.assertEqual(sim["F_slots"][5][:4], [9, 5, 6, 7])
            self.assertEqual(sim["loads"], counts(4, 0, 0))
            self.assertEqual(sim["phases"]["decode"]["CPU"]["hits"], 4)

    def test_diagnostic_relates_to_observed_miss_delta(self):
        start = [list(range(40)) for _ in range(36)]
        target = [set(slots) for slots in start]
        # Each policy sees an identical physical start and series of pinned rank waves.
        work = [
            ("increment", 0, list(range(20))),
            ("increment", 0, list(range(40, 60))),
            ("decode", 0, [60]),
            ("decode", 0, [40, 0]),
        ]
        sims, d = replay(start, target, work)
        a = sims["srrip"]["phases"]["decode"]["CPU"]["misses"]
        b = sims["lru"]["phases"]["decode"]["CPU"]["misses"]
        diag = d["decode"]["CPU"]
        self.assertEqual(diag["excess_srrip_misses"] - diag["excess_lru_misses"], a - b)
        self.assertGreater(diag["different_miss_sets"], 0)


if __name__ == "__main__":
    unittest.main()
