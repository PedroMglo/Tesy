import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().with_name("screen.py")
spec = importlib.util.spec_from_file_location("lexical_decode_screen", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Lexical(unittest.TestCase):
    def test_predict_before_update_and_pruning(self):
        prompt = [1, 2]
        # Layer 35 only has a row for the final external position.
        values = [
            (9, 1, layer, p, (1, 2, 3, 4)) for p in range(2) for layer in range(35 + int(p == 1))
        ]
        values += [
            (10 + i, 1, layer, 2 + i, (8, 9, 10, 11)) for i in range(2) for layer in range(36)
        ]
        plans, _, _ = m.forecasts(prompt, [1, 1], values)
        self.assertEqual(plans[0]["lexical_union"][0], (1, 2, 3, 4))
        self.assertEqual(plans[0]["lexical_union"][35], ())
        self.assertEqual(set(plans[1]["lexical_union"][35]), {8, 9, 10, 11})
        future = [v if v[0] != 11 else (*v[:4], (12, 13, 14, 15)) for v in values]
        self.assertEqual(m.forecasts(prompt, [1, 1], future)[0], plans)
        self.assertEqual(m.forecasts(prompt, [1, 7], values)[0][0], plans[0])

    def test_same_cardinality_with_independent_frequency_order(self):
        history = m.History(1)
        history.observed(1, 0, (4, 5, 6, 7))
        history.observed(2, 0, (0, 1, 2, 3))
        history.observed(2, 0, (0, 1, 2, 3))
        p = history.proposals(1)
        self.assertEqual(p["lexical_union"], [(4, 5, 6, 7)])
        self.assertEqual(p["marginal_matched"], [(0, 1, 2, 3)])
        self.assertEqual(p["lexical_one"], [(4,)])
        self.assertEqual(p["marginal_one"], [(0,)])
        self.assertTrue(all(v == [()] for v in history.proposals(91).values()))

    def test_carry_and_group_maximum(self):
        plans = [{"x": [(2, 3, 4, 5)]}, {"x": [()]}]
        d = {0: [(0, 1, 3, 9)], 1: [(0, 1, 2, 9)]}
        groups = [(0, {0: 7, 1: 3, 3: 6}), (0, {2: 13})]
        r = m.assess("x", plans, d, groups, [{9}], 11)
        t = r["total"]
        self.assertEqual(
            (t["new_prefetches"], t["used_same_step"], t["used_later_step"], t["unused_to_end"]),
            (4, 1, 1, 2),
        )
        self.assertEqual(
            (t["read_floor_us"], t["uncovered_firsts"], t["covered_firsts"]), (7, 2, 2)
        )
        self.assertEqual(t["new_prefetch_plus_remaining_demand_bytes"], 6 * m.first.EXPERT)
        self.assertEqual(r["scales"]["1"]["with_fixed"]["seconds"], 18e-6)

    def test_oracle_gate_applies_to_every_arm(self):
        def row(union, one, marginal, ingress):
            def policy(us, n):
                return dict(
                    total={"read_floor_us": us, "new_prefetches": n},
                    scales={"0.8": {"with_fixed": m.backing.score(us, 0, 4, 5)}},
                )

            return {
                "modes": {
                    "lexical_union": policy(union, 9),
                    "lexical_one": policy(one, ingress),
                    "marginal_one": policy(marginal, 3),
                }
            }

        good = row(1, 2, 3, 2)
        self.assertEqual(m.decide({"a": good}), "GO_PAID_SIMULATION_ONLY")
        self.assertEqual(m.decide({"a": row(1, 2, 3, 4)}), "INCONCLUSIVE")
        self.assertEqual(
            m.decide({"a": good, "b": row(7_000_000, 8_000_000, 9_000_000, 2)}),
            "NO_GO_JOINT_FIXED_REMAINDER",
        )


if __name__ == "__main__":
    unittest.main()
