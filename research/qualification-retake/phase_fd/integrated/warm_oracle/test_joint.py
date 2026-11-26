"""Exhaustive independent pricing of each physically shared selection."""

import importlib.util
import itertools
import unittest
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location(
    "warm_oracle_joint", Path(__file__).with_name("joint.py")
)
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


def brute(prefill, decode, volume, required, fixed, scale):
    universe = sorted(volume | {k for group in decode for k, _ in group})
    answers = []
    for k in range(len(universe) + 1):
        for values in itertools.combinations(universe, k):
            selected = set(values)
            if len(selected & volume) < required:
                continue
            service = 0
            for group in [*prefill, *decode]:
                costs = [cost for key, cost in group if key not in selected]
                service += max([sum(costs) // 4, *costs])
            answers.append((k, fixed + scale[0] * service // scale[1]))
    return answers


class SharedSelection(unittest.TestCase):
    def test_capacity_and_minimum_against_all_subsets(self):
        pref = [[((0, i), t) for i, t in enumerate([3, 3, 4, 4, 4])]]
        dec = [[((1, 0), 8)], [((1, 1), 5)]]
        volume = {(0, i) for i in range(7)}
        caps = range(10)
        for required, scale in itertools.product((0, 3, 7), ((1, 1), (4, 5))):
            possibilities = brute(pref, dec, volume, required, 2, scale)
            for threshold in (1, 2, 7, 15, 28):
                actual = subject.joint(pref, dec, volume, required, 2, scale, threshold, caps)
                min_k = min((k for k, t in possibilities if t <= threshold), default=None)
                minimum = actual["minimum"]
                self.assertEqual(min_k, None if minimum is None else minimum["used"])
                for cap, row in zip(caps, actual["capacity"], strict=True):
                    floor = min((t for k, t in possibilities if k <= cap), default=None)
                    self.assertEqual(floor, row["first_floor_ns"])
                if min_k:
                    before = actual["one_fewer"]["first_floor_ns"]
                    self.assertTrue(before is None or before > threshold)
                if minimum and required == 7:
                    self.assertEqual(minimum["fillers"], 2)

    def test_separate_minima_can_underestimate_joint(self):
        pref = [[((0, 0), 1)]]
        dec = [[((1, 0), 10)]]
        both = subject.joint(pref, dec, {(0, 0), (0, 1)}, 1, 0, (1, 1), 2, [1, 2])
        self.assertEqual(both["minimum"]["used"], 2)
        self.assertEqual(both["one_fewer"]["first_floor_ns"], 10)
        with self.assertRaisesRegex(ValueError, "nonseparable"):
            subject.joint(pref, dec, {(0, 0), (1, 0)}, 1, 0, (1, 1), 2, [2])

    def test_generation_and_inherited_identity(self):
        def row(kind, call, expert, gen, a=0):
            return SimpleNamespace(
                kind=kind, call=call, layer=4, slot=2, gen=gen, expert=expert, a=a
            )

        rows = [row(5, 0, 9, 1, 1), row(5, 0, 6, 1, 2)]
        for expert, generation, dispatch_call in ((9, 2, 1), (6, 2, 2), (3, 1, 2), (5, 3, 3)):
            rows += [row(10, 1, expert, generation), row(13, dispatch_call, expert, generation)]
        rows.append(row(10, 2, 5, 4))
        self.assertEqual(subject.volume_keys(rows), ({(4, 3), (4, 6)}, 1, 1))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            subject.volume_keys([*rows, row(13, 1, 5, 3)])
