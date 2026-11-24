"""The fixture is a synthetic check of event linkage, separate from historical C135."""

import unittest

from current_wave import reload_observations


def fixture():
    rows = []

    def event(kind, expert, slot, wave=0, state=-1, gen=0):
        rows.append(dict(kind=kind, seq=len(rows), wave=wave, layer=0, expert=expert,
                         slot=slot, state=state, generation=gen, call_id=2))

    event("DEMAND", 9, -1, state=0)
    event("EVICT", 12, 7, state=2)
    event("RESERVE", 9, 7)
    event("DEMAND", 18, 11, state=2)
    event("DEMAND", 20, 2, state=2)
    event("DEMAND", 12, -1, state=0)
    event("RESERVE", 12, 5)
    event("LOAD_BEGIN", 12, 5, gen=3)
    return rows


class CurrentWaveTests(unittest.TestCase):
    def test_same_wave_observation(self):
        observation = reload_observations(fixture())
        origin, consumer, source, slot, demand = observation[0, 12, 5, 3]
        self.assertEqual(origin, consumer)
        self.assertEqual((source, slot, demand), (1, 7, 5))

    def test_future_wave_excluded_from_same_wave(self):
        rows = fixture()
        rows[5]["wave"] = 2
        origin, consumer, *_ = reload_observations(rows)[0, 12, 5, 3]
        self.assertEqual((origin[2], consumer[2]), (0, 2))

    def test_absent_consumer(self):
        rows = fixture()
        rows[5].update(state=2, slot=9)
        with self.assertRaisesRegex(ValueError, "did not demand an absent expert"):
            reload_observations(rows)

    def test_nonresident_victim(self):
        rows = fixture()
        rows[1]["state"] = 1
        with self.assertRaisesRegex(ValueError, "not READY"):
            reload_observations(rows)

    def test_resident_created_during_wave(self):
        rows = fixture()
        rows.insert(1, dict(rows[0], kind="LOAD_END", expert=12, slot=7, generation=2))
        for seq, row in enumerate(rows):
            row["seq"] = seq
        with self.assertRaisesRegex(ValueError, "installed during current wave"):
            reload_observations(rows)

    def test_parking_and_next_wave_protection(self):
        rows = fixture()
        rows[3]["kind"] = "WAIT_BEGIN"
        with self.assertRaisesRegex(ValueError, "may borrow parking"):
            reload_observations(rows)
        rows = fixture()
        rows.append(dict(rows[5], wave=1, seq=len(rows)))
        with self.assertRaisesRegex(ValueError, "already-pinned next wave"):
            reload_observations(rows)


if __name__ == "__main__":
    unittest.main()
