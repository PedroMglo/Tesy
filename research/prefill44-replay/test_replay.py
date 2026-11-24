"""Directed worker-free fixtures of the C156 victim order and numerical parking."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from replay import Controller, emit_wave, victim


def layer():
    return dict(
        n_slots=6,
        n_expert=6,
        slot_state=[2] * 6,
        slot_expert=list(range(6)),
        expert_slot=list(range(6)),
        keep=[0] * 6,
        slot_last_use=[7, 6, 5, 4, 3, 2],
        route_hotness=[3, 2, 2, 1, 1, 1],
        use_counter=10,
        pool_used=[],
        expert_wave=[0, 1, 0, 1, 0, 1],
        plan_pool=[2, 0, 4, 3],
        plan_capacity=2,
    )


class ReplayTests(unittest.TestCase):
    def test_exclusion_empty_first_hotness_recency_physical_tie(self):
        sl = layer()
        sl["keep"][5] = 1
        sl["slot_state"][4] = 1
        self.assertEqual(victim(sl), 3)
        sl["slot_state"][1] = 0
        self.assertEqual(victim(sl), 1)
        sl["slot_state"] = [2] * 6
        sl["slot_last_use"][3:5] = [1, 1]
        self.assertEqual(victim(sl), 3)
        sl["keep"] = [1] * 6
        self.assertEqual(victim(sl), -1)

    def test_row_ranks_and_parking_after_real_slots(self):
        sl = layer()
        emit_wave(sl, [2, 1, 0, 3], 0)
        self.assertEqual(sl["pool_used"], [2, 0, 4, 3])
        self.assertEqual(sl["slot_last_use"], [12, 6, 11, 4, 3, 2])
        sl["slot_state"][4] = 1
        with self.assertRaisesRegex(ValueError, "unready parking"):
            emit_wave(sl, [2, 1, 0, 3], 0)

    def test_empty_wave_reuses_four_parking_slots_without_touching_recency(self):
        sl = layer()
        emit_wave(sl, [2, 1, 0, 3], 4)
        self.assertEqual(sl["pool_used"], sl["plan_pool"])
        self.assertEqual(sl["use_counter"], 10)

    def test_wave_plan_advances_without_simple_remap_hotness_decay(self):
        sl = layer()
        for mode in (0, 1):
            c = Controller(
                dict(layers=[sl], workers=4, queue=[], owned=[], n_calls=3, hot_decay_interval=4)
            )
            r = dict(layer=0, call_id=10, ids=[2, 0, 3, 5], mode=mode, n_calls=4)
            c.begin_route(r)
            self.assertEqual(c.sl["uniq"], r["ids"])
            if mode:
                self.assertEqual(c.sl["expert_wave"], [0, 255, 0, 1, 255, 1])
                self.assertEqual(c.sl["route_hotness"], sl["route_hotness"])
            else:
                self.assertEqual(c.sl["route_hotness"], [2, 1, 1, 1, 0, 1])


if __name__ == "__main__":
    unittest.main()
