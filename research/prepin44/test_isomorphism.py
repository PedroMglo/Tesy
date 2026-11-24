import copy
import unittest

from isomorphism import inspect_layer, slot_bijection, summary, victim_order


def example():
    return {
        "slot_expert": [1, -1, 0, -1],
        "slot_state": [2, 0, 2, 0],
        "slot_claimed": [0, 0, 0, 0],
        "slot_gen": [3, 0, 2, 0],
        "slot_last_use": [18, 0, 15, 0],
        "use_counter": 18,
        "keep": [1, 0, 0, 0],
        "expert_slot": [2, 0, -1],
        "plan_pool": [2, 0],
        "demand_slots": [0, 2],
        "pool_used": [2, 0],
        "route_hotness": [2, 2, 0],
        "seen": [1, 1, 0],
        "uniq": [1, 0],
        "touched": [1, 1, 0],
        "expert_wave": [0, 0, 255],
        "n_waves": 1,
        "next_wave": 1,
        "plan_capacity": 2,
    }


class TestRenaming(unittest.TestCase):
    def test_slots_empty_and_nontrivial_offsets(self):
        a = example()
        b = copy.deepcopy(a)
        p = (3, 0, 1, 2)
        for field in (
            "slot_expert",
            "slot_state",
            "slot_claimed",
            "keep",
            "slot_last_use",
            "slot_gen",
        ):
            for s, t in enumerate(p):
                b[field][t] = a[field][s]
        for field in ("demand_slots", "plan_pool", "pool_used"):
            b[field] = [p[s] for s in a[field]]
        b["expert_slot"] = [p[s] if s >= 0 else -1 for s in a["expert_slot"]]
        b["slot_gen"][p[0]] += 4
        self.assertEqual(slot_bijection(a, b), p)
        checks = inspect_layer(a, b, p, [4, 0, 0, 0])
        self.assertEqual(
            {k for k, v in checks.items() if not v}, {"gen_equal", "empty_physical_positions"}
        )
        b["slot_last_use"][p[0]] = 14
        self.assertFalse(inspect_layer(a, b, p, [4, 0, 0, 0])["victim_order_keep_clear"])
        self.assertTrue(inspect_layer(a, b, p, [4, 0, 0, 0])["victim_order_current_keep"])

    def test_physical_tie_is_material(self):
        a = example()
        a["slot_last_use"][0] = a["slot_last_use"][2]
        self.assertEqual(victim_order(a, False), [1, 3, 0, 2])
        self.assertEqual(victim_order(a, True), [1, 3, 2])

    def test_first_difference_and_unequal_lengths(self):
        self.assertEqual(summary([0, 1], [0, 3])["first_difference"], (1, 1, 3))
        self.assertIsNone(summary([0, 1], [0, 1])["first_difference"])
        self.assertEqual(summary([0], [0, 1])["first_difference"], (1, [], [1]))
