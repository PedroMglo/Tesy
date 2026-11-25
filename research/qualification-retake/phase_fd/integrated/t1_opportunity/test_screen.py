"""Independent checks for eligibility, frozen cut and the shared-witness rule."""

import importlib.util
import itertools
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sp = importlib.util.spec_from_file_location(
    "pfj1_opportunity", Path(__file__).with_name("screen.py")
)
m = importlib.util.module_from_spec(sp)
sp.loader.exec_module(m)


def opt(group, s):
    tail = [v for key, v in group if key not in s]
    return max([sum(tail) // 4, *tail])


def row(kind, **kwargs):
    values = {key: 0 for key in m.source.fd.Row._fields}
    values.update(kind=kind, ns=1, layer=-1, slot=-1, expert=-1)
    return m.source.fd.Row(**(values | kwargs))


class WarmOpportunity(unittest.TestCase):
    def test_all_cardinalities_against_independent_enumeration(self):
        groups = [
            [((n, i), cost) for i, cost in enumerate(costs)]
            for n, costs in enumerate(([11, 4, 5, 2, 5, 8], [6, 5], [9]))
        ]
        universe = [k for g in groups for k, _ in g]
        for allow in (set(), set(universe), set(universe[1:-1]), {universe[3], universe[8]}):
            prices, backtrack = m.frontier(groups, allow)
            for n, price in enumerate(prices):
                brute = min(
                    sum(opt(g, selection) for g in groups)
                    for selection in itertools.combinations(allow, n)
                )
                s = backtrack(n)
                self.assertEqual((brute, len(s)), (price, n))
                self.assertLessEqual(s, allow)
                self.assertEqual(sum(opt(g, s) for g in groups), price)

    def test_same_selection_for_volume_and_time(self):
        vol = {(0, 1)}
        allow = vol | {(0, 3)}
        groups = [[((0, 3), 9_000_000_000)], [((0, 1), 1_000_000_000)]]
        rows = m.price(groups, allow, vol, 0, {"contract": 0}, [0, 1, 2])
        self.assertEqual(
            rows[0]["scales"]["1/1"]["decisions"]["contract"], "NO_GO_IN_THIS_OPPORTUNITY"
        )
        self.assertEqual(
            rows[1]["scales"]["1/1"]["decisions"]["contract"], "INCONCLUSIVE_VOLUME_TRADEOFF"
        )
        self.assertEqual(rows[1]["prefill_volume_floor_bytes"], m.warm.PAYLOAD)
        self.assertEqual(rows[2]["prefill_volume_floor_bytes"], 0)
        self.assertEqual(
            rows[2]["scales"]["1/1"]["decisions"]["contract"],
            "HEADROOM_ONLY_CAUSAL_POLICY_REQUIRED",
        )
        no_op = m.price(groups, set(), vol, 2_000_000_000, {"contract": 10**10}, [0])[0]
        self.assertGreater(no_op["scales"]["1/1"]["first_floor_ns"], 10**10)
        self.assertEqual(
            no_op["scales"]["1/1"]["decisions"]["contract"], "NO_GO_IN_THIS_OPPORTUNITY"
        )

    def test_cut_discards_loading_until_publish(self):
        initial = [row(5, call=1, layer=i, slot=j, expert=-1) for i in range(36) for j in range(40)]
        initial[0] = row(5, call=1, layer=0, slot=0, expert=7, gen=1, a=2)
        initial[1] = row(5, call=1, layer=0, slot=1, expert=8, gen=4, a=1, b=1)
        records = [
            row(1, call=1, a=1, b=2119, c=2119),
            *initial,
            row(11, call=1, layer=0, slot=0, expert=9, gen=2, a=7),
            row(2, call=1),
        ]
        _, candidates = m.opportunities(records)
        self.assertEqual(candidates, {"evicted_ready": [(0, 7)], "all_available": [(0, 7)]})
        _, more = m.opportunities([*records, row(17, call=1, layer=0, slot=1, expert=8, gen=4)])
        self.assertEqual(more["all_available"], [(0, 7), (0, 8)])

    def test_failed_capture_stops_before_prefix_or_score(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            gate = p / "receipt.json"
            gate.write_text(json.dumps({"status": "FAIL_PRESERVED"}))
            args = SimpleNamespace(capture_dir=p, capture_sha256=m.sha(gate))
            with patch.object(m, "opportunities", side_effect=AssertionError("opened selection")):
                with self.assertRaisesRegex(ValueError, "terminal capture"):
                    m.seal(args)

    def test_duplicate_key_cannot_be_priced_twice(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            m.frontier([[((0, 0), 3)], [((0, 0), 2)]], {(0, 0)})


if __name__ == "__main__":
    unittest.main()
