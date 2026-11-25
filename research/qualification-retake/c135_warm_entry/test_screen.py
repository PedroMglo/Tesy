import itertools
import unittest

from screen import components, frontier, group_curve


def enumerated(groups, unknowns, layered):
    items = [(i, c, price) for i, two_calls in enumerate(groups)
             for c, group in enumerate(two_calls) for price in group]
    budget = sum(max(0, sum(map(len, pair)) - u) for pair, u in zip(groups, unknowns, strict=True))
    best = [float("inf")] * (budget + 1)
    for bits in itertools.product((False, True), repeat=len(items)):
        credits = sum(max(0, sum(on and i == a for (i, _, _), on in zip(items, bits, strict=True))
                          - unknowns[a]) for a in range(len(groups)))
        residual = [[[] for _ in range(2)] for _ in groups]
        for (layer, call, price), on in zip(items, bits, strict=True):
            if not on:
                residual[layer][call].append(price)
        cost = sum(max(sum(g), 4 * max(g, default=0)) if layered else sum(g)
                   for pair in residual for g in pair)
        for k in range(credits, budget + 1):
            best[k] = min(best[k], cost)
    return best


class TestWarmEntry(unittest.TestCase):
    def test_exhaustive_assignment(self):
        for values in itertools.product((0, 1, 5), repeat=4):
            a, b, c, d = values
            groups = [([a], [b, c]), ([], [d])]
            for unknowns in ([0, 0], [1, 0], [1, 2]):
                for layered in (False, True):
                    self.assertEqual(frontier(groups, unknowns, layered),
                                     enumerated(groups, unknowns, layered))

    def test_joint_start_credit_and_distinct_objectives(self):
        # At k=1 remove the isolated price-3 job for the phase floor, or a price-4 in volume.
        groups = [([3], [4, 4, 4, 4])]
        self.assertEqual(frontier(groups, [0], False)[1], 15)
        self.assertEqual(frontier(groups, [0], True)[1], 16)
        self.assertEqual(frontier(groups, [1], True)[0], 16)

    def test_serial_component_pairing(self):
        def job(layer, slot, start, spans):
            rows = []
            for i, duration in enumerate(spans):
                for kind, stamp in [("READ_BEGIN", start), ("READ_END", start + duration)]:
                    rows.append(dict(call_id=1, layer=layer, expert=7, slot=slot, generation=1,
                                     component=i, kind=kind, logical_bytes=4_406_400, mono_us=stamp))
                start += duration + 2
            return rows
        rows = job(0, 0, 10, [10, 2, 2]) + job(0, 1, 40, [2, 10, 5])
        reference = {"calls": [{"jobs": 2, "read_worker_us": 31}]}
        self.assertEqual(components(rows, reference), {(0, 7): 11})
        rows[2]["mono_us"] = 13  # a later component starts during the first component
        with self.assertRaises(ValueError):
            components(rows, reference)
        with self.assertRaises(ValueError):
            group_curve([-1], True)
