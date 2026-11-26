import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from l2_decode_entry import screen  # noqa: E402


class EntryAuditTests(unittest.TestCase):
    @staticmethod
    def row(kind, call, gen):
        return dict(kind=kind, call=call, layer=1, expert=4, slot=7, gen=gen)

    def test_distinct_generations_across_i(self):
        rows = [self.row(5, 0, 1), self.row(10, 0, 1), self.row(5, 1, 2), self.row(10, 1, 2)]
        jobs = {"increment": [(0, 1, (1, 4))], "decode": [(2, 3, (1, 4))]}
        self.assertEqual(screen.claim_index(rows, jobs), {2: (1, 4, 7, 2)})
        for field, broken in (("gen", 1), ("slot", 0), ("expert", 1), ("call", 0), ("kind", 9)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                screen.claim_index([*rows[:3], {**rows[3], field: broken}], jobs)

    def test_reservation_bitmap(self):
        layers = [{"layer": i, "seen": [0] * 128} for i in range(36)]
        layers[7]["seen"][61] = 1
        self.assertEqual(screen.reserved_keys({"layers": layers}), {(7, 61)})
        layers[1]["seen"][45] = True
        with self.assertRaises(ValueError):
            screen.reserved_keys({"layers": layers})

    def test_joint_decision_rejects_one_failed_repetition(self):
        def arm(upper, feasible):
            return {
                "eligibility": {
                    "any": {"by_capacity": {1: {"optimistic": {"scales": [{"reaches_6": upper}]}}}},
                    "prefix_routed": {
                        "by_capacity": {1: {"feasible": {"scales": [{"reaches_6": feasible}]}}}
                    },
                }
            }

        arms = {
            f"c294-{case}-{rep}-on": arm(True, False) for case in screen.p.PROMPT for rep in (2, 3)
        }
        arms["c294-nominal153-3-on"] = arm(False, False)
        self.assertEqual(
            screen.classify(arms, 1, 0),
            {
                "nominal153": "NO_GO_CAPACITY_BOTH_REPEATS_REQUIRED",
                "code153": "INCONCLUSIVE",
            },
        )


if __name__ == "__main__":
    unittest.main()
