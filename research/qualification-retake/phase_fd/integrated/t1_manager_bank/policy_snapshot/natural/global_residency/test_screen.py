import itertools
import unittest
from pathlib import Path
from runpy import run_path

m = run_path(str(Path(__file__).with_name("screen.py")))


def brute(waves, cap, initial, free):
    costs = {frozenset(initial): 0}
    for row in waves:
        req = set(row)
        updated = {}
        for state, cost in costs.items():
            miss = cost + len(req - state - free)
            for n in range(min(cap - len(req), len(state - req)) + 1):
                for keep in itertools.combinations(state - req, n):
                    result = frozenset(req.union(keep))
                    updated[result] = min(updated.get(result, 100000), miss)
        costs = updated
    return min(costs.values())


class GlobalTests(unittest.TestCase):
    def test_exact_witness_against_enumeration(self):
        choices = ([0], [1], [2], [3], [0, 1], [1, 2], [2, 3])
        for waves in itertools.product(choices, repeat=3):
            for init in ({0}, {0, 1}):
                for free in (set(), {0, 2}):
                    history, resident = m["schedule"](waves, 2, init, free)
                    self.assertEqual(sum(len(d) for d, b in history), brute(waves, 2, init, free))
                    self.assertTrue(set(waves[-1]) <= resident)
        with self.assertRaisesRegex(ValueError, "wave"):
            m["schedule"]([[0, 1, 2]], 2, {0, 1}, {0})
        with self.assertRaisesRegex(ValueError, "entry"):
            m["schedule"]([[0, 1]], 1, {0, 1}, {0})

    def test_pooling_preserves_namespaces_and_terminal(self):
        pins = [[0], [1], [0], [128], [128]]
        groups = [{"site": (0, 1, k[0] // 128, -1), "pins": k} for k in pins]
        initial = {0, 128}
        shared, _ = m["solve"](groups, initial, set(), 2, False)
        per, _ = m["solve"](groups, initial, set(), 1, True)
        self.assertEqual(sum(len(d) for d, b in shared), 2)
        self.assertEqual(sum(len(d) for d, b in per), 2)
        # Layer 1's idle second slot can benefit layer 0 when decoding three experts repeatedly.
        harder = [dict(site=(0, 0, 0, -1), pins=[i]) for i in [0, 1, 2, 0, 1, 2]]
        fixed, _ = m["solve"](harder, initial, set(), 1, True)
        pooled, extra = m["solve"](harder, initial, set(), 2, False, terminal={1, 128})
        self.assertLess(sum(len(d) for d, b in pooled), sum(len(d) for d, b in fixed))
        self.assertGreaterEqual(extra["disk"], 1)

    def test_logical_ready_without_backing_and_cuda_clock(self):
        cpu = dict(
            site=(0, 1, 0, -1), pins=[3], new_demand=set(), phase="decode", logical_disk=set()
        )
        cuda = dict(
            site=(0, 1, 25, -1),
            pins=[3201],
            new_demand={3201},
            phase="decode",
            logical_disk={3201},
            logical_bank=1,
        )
        events = [((3,), ()), ((), ())]
        record = m["summarize"]([cpu, cuda], events)["decode"]
        self.assertEqual(record["cpu_logical_hit_disk"], 1)
        self.assertEqual(record["cuda_disk"], 1)
        prices = m["decode_prices"]([cpu, cuda], events, {"RP": [({4: 50}, 80), ({3201: 36}, 65)]})[
            "RP"
        ]
        self.assertEqual(prices["cpu_read_unpriced"], 1)
        self.assertEqual(prices["decode_witness_ns"], 2_318_241_276 + 65)
        self.assertEqual(prices["cpu_read_priced"], 0)


if __name__ == "__main__":
    unittest.main()
