import unittest
from pathlib import Path
from runpy import run_path

module = run_path(Path(__file__).with_name("screen.py"))
decode = module["decode_wave"]
ONE = 0x3F800000
RANKS = [(1, 2), (3, 1)]
MASKS = [[ONE, ONE, 0, ONE], [0, 0, ONE, 0], [0] * 4]
IDS = [[0, 1, -1, 0], [-1, -1, 0, -1], [-1] * 4]


def evaluate(ids=IDS, masks=MASKS, skip=True):
    return decode(list(zip(ids, masks, strict=True)), RANKS, 2, 4, skip)


class TestWitness(unittest.TestCase):
    def test_geometry_from_width(self):
        self.assertEqual(module["geometry"](29, 40, 4), (18, 7))
        self.assertEqual(module["geometry"](32, 40, 4), (18, 8))
        with self.assertRaises(ValueError):
            module["geometry"](1, 40, 4)

    def test_replacement_and_empty_wave(self):
        owners, report = evaluate()
        self.assertEqual(owners, {0: (3, 1), 1: (2, 0)})
        self.assertEqual([r["active_ranks"] for r in report], [3, 1, 0])
        self.assertEqual(report[2]["masked_ranks"], 4)
        with self.assertRaises(ValueError):
            evaluate(IDS[:1], MASKS[:1])

    def test_concrete_parking_has_no_owner(self):
        ids = [[0, 1, 1, 0], [1, 2, 0, 1], [2, 3, 2, 3]]
        self.assertEqual(evaluate(ids, skip=False)[0], evaluate()[0])
        with self.assertRaises(ValueError):
            evaluate(ids)

    def test_simultaneous_alias_and_moved_owner(self):
        for first in ([0, 0, -1, 0], [0, 1, -1, 2]):
            with self.subTest(first=first), self.assertRaises(ValueError):
                evaluate([first, *IDS[1:]])

    def test_wrong_wave_and_corrupt_zero(self):
        for first in ([ONE, 0, ONE, ONE], [ONE, ONE, 0x80000000, ONE]):
            with self.subTest(first=first), self.assertRaises(ValueError):
                evaluate(masks=[first, *MASKS[1:]])


if __name__ == "__main__":
    unittest.main()
