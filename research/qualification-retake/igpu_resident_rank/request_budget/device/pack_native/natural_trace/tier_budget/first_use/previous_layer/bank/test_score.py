import unittest
from pathlib import Path
from runpy import run_path

S = run_path(str(Path(__file__).with_name("score.py")))
RATE = 8_000_000_000
TICKS = S["SIZE"] // 8


class Combined(unittest.TestCase):
    def test_covered_bytes_are_not_charged_twice(self):
        r = S["cross"]([(3, 1, 2, 3 * TICKS), (2, 0, 1, 0)], RATE, False, TICKS)
        ns = r["ns"]
        self.assertEqual(ns["combined"], 2 * TICKS)
        self.assertEqual(ns["overlapping_saving"], TICKS)
        self.assertEqual(ns["last353_marginal_after_previous"], 0)
        self.assertEqual(r["minimum_extra_useful_selections_from_offers"], 1)

    def test_whole_partial_and_no_additional_option(self):
        cells = [(3, 1, 1, TICKS + TICKS // 2)]
        p, w = (S["cross"](cells, RATE, b, 0) for b in (False, True))
        self.assertEqual(p["ns"]["combined"], TICKS // 2)
        self.assertEqual(w["ns"]["combined"], TICKS)
        self.assertIsNone(w["minimum_extra_useful_selections_from_offers"])
        with self.assertRaises(ValueError):
            S["cross"]([(1, 1, 0, 0)], RATE, False, 0)

    def test_conserved_marginal_selections(self):
        cells = [(4, 0, 3, TICKS + TICKS // 2), (2, 0, 1, TICKS + TICKS // 2)]
        r = S["cross"](cells, RATE, False, TICKS // 2)
        self.assertEqual(r["ns"]["combined"], 3 * TICKS)
        self.assertEqual(r["ns"]["offers_combined"], 0)
        self.assertEqual(r["minimum_extra_useful_selections_from_offers"], 3)
        self.assertEqual(
            S["cross"](cells, RATE, False, 3 * TICKS)[
                "minimum_extra_useful_selections_from_offers"
            ],
            0,
        )


if __name__ == "__main__":
    unittest.main()
