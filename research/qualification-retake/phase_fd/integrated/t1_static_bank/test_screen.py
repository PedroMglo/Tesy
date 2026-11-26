import importlib.util
import itertools
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location(
    "protected_bank", Path(__file__).with_name("screen.py")
)
bank = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bank)


def event(kind, call, gen, component=-1):
    return SimpleNamespace(
        kind=kind,
        call=call,
        gen=gen,
        component=component,
        layer=0,
        slot=1,
        expert=4,
        b=8 if kind == 15 else 0,
        c=6 if kind == 15 else 0,
    )


def job(call, gen):
    return [
        event(13, call, gen),
        *(event(15, call, gen, c) for c in (2, 0, 1)),
        event(17, call, gen),
    ]


class Tests(unittest.TestCase):
    def test_padding_repeat_and_cut(self):
        cut = event(2, 2, 0)
        events = job(1, 1) + job(2, 2) + [cut] + job(3, 3)
        byte, pre, dec = bank.totals(events)
        self.assertEqual((byte.total(), pre.total(), dec.total()), (36, 2, 1))
        with self.assertRaises(ValueError):
            bank.totals(events[:1] + [cut] + events[1:])

    def test_duplicate_component(self):
        rows = job(2, 1) + [event(2, 2, 0)]
        rows[2] = rows[1]
        with self.assertRaises(ValueError):
            bank.totals(rows)

    def test_joint(self):
        self.assertEqual(
            bank.classify({"a": (1, 1, 0, 1), "b": (0, 0, 1, 1)}), "INCONCLUSIVE_JOINT_SELECTION"
        )
        self.assertEqual(
            bank.classify({"a": (1, 1, 0, 1), "b": (1, 1, 0, 1)}), "NO_GO_FIXED_T1_BANK"
        )
        self.assertEqual(bank.classify({"a": (1, 1, 1, 1)}), "HEADROOM_ONLY_PRICE_COPIES")

    def test_against_enumeration(self):
        keys = [(0, i) for i in range(8)]
        groups = [list(zip(keys[:6], (18, 16, 14, 11, 9, 8), strict=True)), [(keys[6], 21)]]
        allowed = set(keys[:5] + keys[6:])
        p = Counter({k: i + 9 for i, k in enumerate(keys)})
        d = Counter({k: 10 - i for i, k in enumerate(keys)})
        inputs = (p, Counter({k: 1 for k in keys}), d)
        caps = (0, 1, 3, len(allowed))
        rows = bank.screen(groups, allowed, inputs, 5, {"47": 40}, 10**12, caps)
        for k, row in zip(caps, rows, strict=True):
            results = [
                bank.witness(s, *inputs, groups, 5) for s in itertools.combinations(allowed, k)
            ]
            witnesses = row["witnesses"]
            for name, metric, fn in (
                ("volume", "prefill_return_bytes_saved", max),
                ("decode", "decode_hits", max),
                ("time", "raw_floor_ns", min),
            ):
                self.assertEqual(witnesses[name][metric], fn(r[metric] for r in results))


if __name__ == "__main__":
    unittest.main()
