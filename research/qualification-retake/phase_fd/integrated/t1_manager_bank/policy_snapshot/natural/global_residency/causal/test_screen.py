import unittest
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

m = run_path(Path(__file__).with_name("screen.py"))
LRU = m["LRU"]


class CausalPolicy(unittest.TestCase):
    def test_demand_only_prefix_and_tie(self):
        rows = [
            SimpleNamespace(kind=k, layer=layer, expert=e)
            for k, layer, e in [(10, 2, 8), (17, 0, 7), (10, 25, 1), (10, 2, 1), (10, 2, 8)]
        ]
        last, clk = m["last_uses"](rows)
        self.assertEqual((last, clk), ({264: 3, 257: 2}, 3))
        pool = LRU(4, [0, 1, 257, 264], last, clk)
        self.assertEqual(pool.serve([2]), ([2], [0]))
        self.assertEqual(pool.serve([3]), ([3], [1]))

    def test_batch_pins_promotions_and_future(self):
        def run(tail):
            pool = LRU(3, [0, 1, 2], {}, 0)
            first = pool.serve([3, 0])
            second = pool.serve([4, 0])
            before = dict(pool.ages)
            third = pool.serve(tail)
            return first, second, before, third

        a, b = run([2]), run([1, 3])
        self.assertEqual(a[:3], b[:3])
        self.assertEqual(a[0], ([3], [1]))
        self.assertEqual(a[1], ([4], [2]))
        self.assertLess(a[2][4], a[2][0])
        self.assertEqual(a[3][1], [3])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            LRU(2, [], {}, 0).serve([1, 1])

    def test_bank_and_layer(self):
        groups = [
            dict(site=(1, 1, 0, 0), phase="call5", pins=[4, 5]),
            dict(site=(2, 1, 1, 0), phase="decode", pins=[133]),
        ]
        for name in ("P40", "P1000", "U1262"):
            events, _ = m["simulate"](groups, {4}, {5}, {}, 0, name)
            self.assertEqual(events[0], ((), () if name == "U1262" else (5,)))
            self.assertEqual(events[1], ((133,), ()))

    def test_unknown_cost(self):
        f = m["unknown_budget"]
        self.assertEqual(f([3, 10], 20, 25)["max_uniform_ns"], 8)
        self.assertEqual(f([3, 3], 10, 11)["max_uniform_ns"], 3)
        self.assertEqual(f([3], 10, 9)["status"], "NO_ROOM_AT_ZERO")
        self.assertEqual(f([], 1, 2)["status"], "NO_UNPRICED_READ")

    def test_price_different_wave_does_not_transfer(self):
        a, b = (3, 1, 0, 0), (3, 1, 0, 1)
        c = (3, 1, 25, 0)
        g = [
            dict(phase="call5", site=a),
            dict(phase="call5", site=b),
            dict(phase="call5", site=c, logical_disk={3201}),
        ]
        prices = {(a, 10): 17, (c, 3201): 21}
        got = m["prefill_coverage"](g, [((10,), ()), ((10,), ()), ((), ())], prices)["call5"]
        self.assertEqual(dict(got["cpu"]), {"priced": 1, "unpriced": 1, "read_worker_ns": 17})
        self.assertEqual(dict(got["cuda"]), {"priced": 1, "read_worker_ns": 21})


if __name__ == "__main__":
    unittest.main()
