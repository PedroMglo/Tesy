import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("parked_gate", Path(__file__).with_name("decision.py"))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def schedule(deltas):
    return [
        dict(mode=mode, graph_ns=7_000_000 - (deltas[i // 2] if mode == "ON" else 0))
        for i, mode in enumerate(gate.ORDER)
    ]


class PairedGate(unittest.TestCase):
    def test_both_orders_and_threshold_inclusive(self):
        s = [7, 900_000, 1_100_000, 2_100_000]
        out = gate.evaluate(schedule(s))
        self.assertEqual("GO_TEST_NEXT", out["decision"])
        self.assertEqual(1_000_000, out["median_saved_ns"])
        self.assertEqual(s, [p["saved_ns"] for p in out["pairs"]])

    def test_zero_and_mixed_signs(self):
        self.assertEqual("NO_GO_CPU0_TILE", gate.evaluate(schedule([0, -1, 0, -3]))["decision"])
        for s in ([1, 2, 3, 4], [-1, 2_000_000, 2_000_000, 2_000_000]):
            self.assertEqual("INCONCLUSIVE", gate.evaluate(schedule(s))["decision"])

    def test_bad_order_and_invalid_clock(self):
        rows = schedule([1] * 4)
        with self.assertRaises(ValueError):
            gate.evaluate(rows[::-1][1:])
        for x in (True, -1, 0, 5.0):
            with self.assertRaises(ValueError):
                gate.evaluate([rows[0] | {"graph_ns": x}, *rows[1:]])
