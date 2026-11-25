"""Small, explicit equivalence and fault controls for the natural policy reconstruction."""

import unittest
from collections import Counter

import manager
import screen


def init(calls=0, backed=()):
    bank = [set() for _ in range(36)]
    bank[0].update(backed)
    states = [(s, 1, 2, 0) for _ in range(36) for s in range(40)]
    words = [(40, *range(1, 41), *([0] * 128)) for _ in range(36)]
    return manager.Manager(states, words, calls, 2304, bank)


class TestNativeDecisions(unittest.TestCase):
    def test_source_scoring_saturation_decay_and_rank_order(self):
        m = init(2303)
        m.pools[2].heat[2] = 31
        m.pools[0].heat[55] = 2**32 - 2
        new, demands = m.callback(0, -1, [55, 55 - 1, 57, 3])
        self.assertEqual(new, [(55, 0, 2, 0, 0), (54, 1, 2, 1, 0), (57, 2, 2, 2, 0)])
        self.assertEqual(demands, [(55, 0, 2), (54, 1, 2), (57, 2, 2), (3, 3, 1)])
        self.assertEqual(m.pools[0].heat[55], (2**32 - 2) // 2)
        self.assertEqual(m.pools[2].heat[2], 15)
        self.assertEqual(m.pools[0].ages[:4], [44, 45, 46, 47])

    def test_even_an_upcoming_demand_can_be_evicted_before_keep(self):
        m = init()
        m.pools[0].heat[:40] = [9] * 40
        m.pools[0].heat[:3] = [0, 1, 2]
        new, _ = m.callback(0, -1, [41, 0, 1, 2])
        self.assertEqual(new[:2], [(41, 0, 2, 0, 0), (0, 1, 2, 1, 0)])
        self.assertEqual([x[0] for x in new], [41, 0, 1, 2])

    def test_empty_precedes_backed_and_keep_is_authoritative(self):
        m = init(backed=[35, 36])
        p = m.pools[0]
        p.ids[1] = -1
        self.assertEqual(manager.victim(p, set(), m.bank[0]), 1)
        self.assertEqual(manager.victim(p, {1, 35}, m.bank[0]), 36)
        self.assertEqual(manager.victim(p, {1, 35, 36}, m.bank[0]), 0)

    def test_next_wave_and_parking_do_not_require_publication_order(self):
        m = init()
        # 21 distinct, 11 tokens top-4, 3 graph waves; the last is entirely parking.
        seq = [s % 21 + 40 for s in range(44)]
        original = m.pools[0].heat[:]
        w0, _ = m.callback(0, 0, seq)
        self.assertEqual([e[4] for e in w0], [0] * 18 + [2] * 3)
        self.assertEqual(m.pools[0].possible_loading, set(seq[18:21]))
        old = m.pools[0].parking[:]
        w1, d = m.callback(0, 1, seq)
        self.assertEqual(w1, [])
        self.assertEqual(m.pools[0].parking, [v[1] for v in d] + old[:1])
        self.assertEqual(m.pools[0].heat, original)
        ages = m.pools[0].ages[:]
        self.assertEqual(m.callback(0, 2, seq), ([], []))
        self.assertEqual(ages, m.pools[0].ages)
        self.assertEqual(m.calls, 1)

    def test_unrelated_loading_and_reordered_or_missing_wave_fail(self):
        m = init()
        m.pools[0].possible_loading = {38}
        with self.assertRaises(manager.OrderUnknown):
            m.callback(0, -1, [0, 1, 2, 3])
        m = init()
        seq = [s % 21 + 40 for s in range(44)]
        m.callback(0, 0, seq)
        with self.assertRaises(ValueError):
            m.callback(0, 2, seq)
        with self.assertRaises(ValueError):
            m.callback(0, 1, seq[::-1])

    def test_restore_same_members_nontrivial_cycle_and_actual_source(self):
        m = init()
        ref = init()
        m.pools[0].ids[:3] = [1, 0, 50]
        bank = m.bank
        bank[0].add(2)
        c = screen.by_tier()
        detail = manager.repair(m, ref, bank, {}, c)
        self.assertEqual(
            (detail["cycles"], detail["same_tier_slot_moves_cpu"], detail["missing_members"]),
            (1, 2, 1),
        )
        self.assertEqual(c["cpu"]["bank_hits"], 1)
        self.assertEqual(c["cpu"]["disk_jobs"], 0)
        self.assertEqual(detail["slot_move_payload_bytes_cpu"], 2 * manager.PAYLOAD)

    def test_r0_mutated_observed_slot_and_promotion_are_rejected(self):
        m = init()
        ranks = [1, 2, 3, 4]
        groups = [
            dict(
                site=(c, 1, 0, -1), new=[], demands=[(e, e, 1) for e in ranks], ranks=ranks, rows=1
            )
            for c in (1, 2, 3)
        ]
        states = [(s, 1, 2, 0) for _ in range(36) for s in range(40)]
        words = [(40, *range(1, 41), *([0] * 128)) for _ in range(36)]
        args = (groups, Counter(), states, words, 0, 2304, m.bank, [[]] * 36)
        _, screened = screen.trajectory(*args, priority=False, restore=False, reference=None)
        self.assertEqual(screened["r0_sites_checked"], 3)
        groups[1]["demands"][2] = (3, 9, 1)
        with self.assertRaisesRegex(ValueError, "R0 decision mismatch"):
            screen.trajectory(*args, priority=False, restore=False, reference=None)
        fake = screen.fd.Row(*([0] * 18))._replace(kind=12, a=1)
        with self.assertRaisesRegex(ValueError, "promotion"):
            screen.segment([fake])


if __name__ == "__main__":
    unittest.main()
