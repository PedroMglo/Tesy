import unittest
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
S = run_path(str(HERE / "state.py"))
SEL = S["SELECT"]


class TestReplay(unittest.TestCase):
    def test_order_and_unavailable_reference(self):
        xs = [
            (2, 0, [1, 2, 3, 4], [2], [0]),
            (2, 1, [2, 3, 4, 5], [], []),
            (3, 0, [5, 4, 3, 2], [2], []),
            (3, 1, [1, 2, 3, 4], [2], []),
        ]
        chosen, visited = SEL["select"](xs)
        self.assertEqual(chosen, xs[2])
        self.assertEqual(len(visited), 3)
        self.assertEqual(visited[0]["reasons"], ["missing_independent_golds"])

    def test_pitched_29_and_corruption(self):
        q = bytes(range(16))
        data = (q + b"\xff" * 496) * 28 + q
        r = dict(
            name="ffn_moe_topk",
            ne="4,29,1,1",
            nb="4,512,14848,14848",
            type="i32",
            bytes=str(len(data)),
        )
        self.assertEqual(SEL["array"](r, data, 29), ("ids.i32", q * 29))
        with self.assertRaisesRegex(ValueError, "descriptor"):
            SEL["array"](dict(r, nb="4,16,464,464"), data, 29)

    def test_victim_and_demand_are_independent(self):
        x = [(3, 4, 2, 18, 0)]
        demands = [(3, 4, 2)]
        S["compare_decisions"]((1, 5, 0, 0), x, x, demands, demands)
        with self.assertRaisesRegex(ValueError, "victim"):
            S["compare_decisions"]((), x, [(3, 4, 2, 19, 0)], demands, demands)
        with self.assertRaisesRegex(ValueError, "binding"):
            S["compare_decisions"]((), x, x, demands, [(3, 4, 1)])


if __name__ == "__main__":
    unittest.main()
