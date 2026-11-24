import unittest

from policy import Fixture


def data():
    residents = [3, 1, 2, 4, 5, 6, 7, 8]
    sl = {
        "layer": 0,
        "slot_expert": residents,
        "expert_slot": [residents.index(e) if e in residents else -1 for e in range(10)],
        "n_slots": 8,
        "n_expert": 10,
        "plan_capacity": 4,
        "plan_pool": [0, 1, 2, 3],
        "slot_state": [2] * 8,
        "slot_claimed": [0] * 8,
        "slot_last_use": list(range(1, 9)),
        "slot_gen": [1] * 8,
        "route_hotness": [0] * 10,
        "seen": [1] * 10,
        "use_counter": 8,
    }
    return {
        "layers": [sl],
        "queue": [],
        "owned": [],
        "workers": 4,
        "next_work_id": 8,
        "n_calls": 0,
        "hot_decay_interval": 0,
    }


class PolicyTest(unittest.TestCase):
    def test_resident_survives_first_miss(self):
        route = {"call_id": 10, "layer": 0, "mode": 1, "n_calls": 1, "ids": list(range(8))}
        for mode in ("early", "late"):
            off, on = (Fixture(data(), mode, active) for active in (False, True))
            off.run([route])
            on.run([route])
            self.assertEqual([x[2] for x in off.reservations], [0, 3])
            self.assertEqual([x[2] for x in on.reservations], [0])
            self.assertEqual(
                set(off.s["layers"][0]["slot_expert"]), set(on.s["layers"][0]["slot_expert"])
            )
            self.assertNotEqual(off.s["layers"][0]["slot_expert"], on.s["layers"][0]["slot_expert"])

    def test_inherited_loader_is_rejected(self):
        init = data()
        init["layers"][0]["slot_state"][0] = 1
        with self.assertRaisesRegex(ValueError, "pending generation escapes"):
            Fixture(init, "early", True).run(
                [{"call_id": 10, "layer": 0, "mode": 1, "n_calls": 1, "ids": list(range(8))}]
            )
