import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from srrip40.policy import Pool  # noqa: E402


class PhysicalReplacement(unittest.TestCase):
    def test_unknown_history_evicts_lowest_eligible_physical_slot(self):
        for rule in ("lru", "srrip"):
            pool = Pool(reversed(range(40)), rule)
            stats = pool.serve([106, 39, 105, 106])
            self.assertEqual(pool.slots[:4], [39, 106, 105, 36])
            self.assertEqual(
                stats,
                dict(
                    misses=2,
                    hits=1,
                    evictions=2,
                    distinct_demands=3,
                    rank_uses=4,
                    waves=1,
                    parking_only_waves=0,
                ),
            )

    def test_empty_slots_in_physical_order_before_eviction(self):
        slots = list(range(40))
        slots[7] = slots[19] = -1
        for rule in ("lru", "srrip"):
            pool = Pool(slots, rule)
            stats = pool.serve([91, 92, 0, 93])
            self.assertEqual([pool.slots[i] for i in (0, 7, 19, 1)], [0, 91, 92, 93])
            self.assertEqual((stats["misses"], stats["hits"], stats["evictions"]), (3, 1, 1))

    def test_srrip_multiple_ages_pins_and_insertion_vs_reuse(self):
        # All entries hit once; their RRPVs become zero. Expert 0 is protected through the
        # next three aging increments. Expert 40 enters slot 1, where its second rank aliases
        # the first miss. An actual later hit makes its priority equal to expert 0.
        for later_hit, victim in ((False, 40), (True, 0)):
            pool = Pool(range(40), "srrip")
            pool.serve(range(40))
            pool.serve([40, 0, 40])
            self.assertEqual(pool.slots[:2], [0, 40])
            if later_hit:
                self.assertEqual(pool.serve([40])["hits"], 1)
            pool.serve([41, *range(2, 40)])
            self.assertNotIn(victim, pool.slots)
            self.assertEqual(set(pool.slots[2:]), set(range(2, 40)))

    def test_lru_uses_first_occurrence_within_wave(self):
        pool = Pool(range(40), "lru")
        pool.serve([38, 39, *range(38), 38])
        pool.serve([76])
        self.assertEqual(pool.slots[38], 76)
        self.assertIn(39, pool.slots)

    def test_empty_wave_and_failed_inputs_cannot_change_next_victim(self):
        for rule in ("srrip", "lru"):
            a, b = (Pool(range(40), rule) for _ in range(2))
            self.assertEqual(
                a.serve([]),
                dict(
                    misses=0,
                    hits=0,
                    evictions=0,
                    distinct_demands=0,
                    rank_uses=0,
                    waves=0,
                    parking_only_waves=1,
                ),
            )
            for invalid in ([-1], [128], [False], range(41)):
                with self.assertRaises(ValueError):
                    a.serve(invalid)
            a.slots[0] = 70
            for wave in ([102, 2, 3], [77], [2], [90, 91]):
                self.assertEqual(a.serve(wave), b.serve(wave))
                self.assertEqual(a.slots, b.slots)

    def test_rejects_invalid_start(self):
        for slots, rule in (
            ([0] * 40, "lru"),
            ([-1] * 39, "srrip"),
            (range(40), "future"),
            ([127] * 39 + [False], "lru"),
            ([-1] * 39 + [128], "lru"),
        ):
            with self.assertRaises(ValueError):
                Pool(slots, rule)


if __name__ == "__main__":
    unittest.main()
