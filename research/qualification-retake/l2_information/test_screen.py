import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from l2_information.screen import assess, classify  # noqa: E402


class Information(unittest.TestCase):
    def test_four_distinct_classes_check_left_publication(self):
        a, b, c, d = (0, 1), (0, 2), (26, 1), (26, 2)
        jobs = {
            "increment": [(0, 1, a), (2, 3, b), (4, 5, b)],
            "decode": [
                (6, 7, c),
                (8, 9, c),
                (10, 11, d),
                (12, 13, d),
                (14, 15, d),
                (16, 17, a),
                (18, 19, b),
            ],
        }
        groups, split = classify(jobs)
        self.assertEqual(
            {k: [(a, b) for a, b, _ in v] for k, v in groups.items()},
            {
                "full": [(7, 8), (11, 12), (13, 14), (1, 16), (5, 18)],
                "no_first_publication": [(13, 14), (5, 18)],
                "no_carry_from_increment": [(7, 8), (11, 12), (13, 14)],
                "neither": [(13, 14)],
            },
        )
        self.assertEqual(split["repeat", "decode", "CUDA0"], 1)
        self.assertEqual(split["first", "increment", "CPU"], 1)
        self.assertEqual(sum(split.values()), 5)

    def test_shortfalls_are_not_additive(self):
        jobs = {
            "increment": [(0, 1, (0, 1)), (2, 3, (26, 1))],
            "decode": [(4, 5, (0, 1)), (6, 7, (26, 1))],
        }
        groups, _ = classify(jobs)
        report = assess(groups, 2, 6)
        self.assertEqual(report["ceil_20pct_hits"], 2)
        res = report["restrictions"]
        self.assertEqual(res["full"]["ceiling_hits"], 2)
        self.assertEqual(
            [
                res[k]["gate_shortfall_hits"]
                for k in ("no_first_publication", "no_carry_from_increment", "neither")
            ],
            [2, 2, 2],
        )
        self.assertEqual(assess(groups, 1, 6)["restrictions"]["full"]["ceiling_hits"], 1)


if __name__ == "__main__":
    unittest.main()
