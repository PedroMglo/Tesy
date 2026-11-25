import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "fusion_gate", Path(__file__).with_name("decision.py")
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def schedule(fusion_ns):
    rows = []
    for order, f in zip(gate.BLOCKS, fusion_ns, strict=True):
        values = dict(ORIGINAL=20_000_000, MMID=20_000_000, FUSION=f)
        rows.extend(dict(mode=k, graph_ns=values[k]) for k in order)
    return rows


class RegisteredGate(unittest.TestCase):
    def test_boundary(self):
        rows = schedule([19_000_000] * 6)
        self.assertEqual(gate.evaluate(rows)["decision"], "GO_DIVERSE_TILES")
        self.assertEqual(gate.evaluate(schedule([19_000_001] * 6))["decision"], "INCONCLUSIVE")
        self.assertEqual(gate.evaluate(schedule([20_000_000] * 6))["decision"], "NO_GO_CPU0_TILE")
        rows[0]["graph_ns"] = 19_000_000
        self.assertEqual(gate.evaluate(rows)["decision"], "INCONCLUSIVE")

    def test_even_one_comparator_can_close_the_variant(self):
        rows = schedule([18_000_000] * 6)
        for r in rows:
            if r["mode"] == "MMID":
                r["graph_ns"] = 17_900_000
        self.assertEqual(gate.evaluate(rows)["decision"], "NO_GO_CPU0_TILE")
        with self.assertRaises(ValueError):
            gate.evaluate(rows[1:])
        rows[2]["graph_ns"] = True
        with self.assertRaises(ValueError):
            gate.evaluate(rows)
