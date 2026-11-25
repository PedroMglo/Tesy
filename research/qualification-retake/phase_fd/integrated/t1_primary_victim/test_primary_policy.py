import unittest
from collections import Counter
from pathlib import Path
from runpy import run_path

api = run_path(str(Path(__file__).with_name("screen.py")))


class PrimaryPolicyTest(unittest.TestCase):
    def test_resident_in_ram_is_cheaper_even_if_recent(self):
        for prefer, expected in ((False, [3, 2]), (True, [1, 3])):
            pool = api["Pool"]([1, 2])
            pool.age = [1, 2]
            pool.wave(0, [3], {(0, 2)}, prefer, 3, Counter())
            self.assertEqual(pool.slots, expected)

    def test_pins_and_restoration(self):
        pool = api["Pool"]([1, 2])
        counts = Counter()
        pool.wave(0, [2, 3], {(0, 2)}, True, 1, counts)
        self.assertEqual(pool.slots, [3, 2])
        pool.restore(0, [1, 2], {(0, 1)}, 2, counts)
        self.assertEqual((counts["ram"], counts["disk"]), (1, 1))
        self.assertEqual(pool.age, [2, 1])

    def test_floor_and_restoration_gate(self):
        args = ([[1, -1]], [[3, 4]], [(1, 0, [1]), (2, 0, [2]), (3, 0, [4])], {(0, 3)})
        for restore, floor, count in ((False, 1, 1), (True, 2, 0)):
            arm = api["evaluate"](*args, True, restore, {"47": 2 * api["PAYLOAD"]})
            self.assertEqual(arm["compulsory_cold_keys"], floor)
            self.assertEqual(arm["decode"].get("disk", 0), count)
            self.assertTrue(arm["scenario"]["47"]["joint"])
