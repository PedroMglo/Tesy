import unittest
from pathlib import Path
from runpy import run_path

F = run_path(str(Path(__file__).with_name("score.py")))


class SuffixBudget(unittest.TestCase):
    def test_partial_block_counts_serial_row_and_one_anchor(self):
        rows = [("ar", 60, 0, 20), ("anchor", 100, 40, 16), ("skip", 80, 30, 12)]
        fixed = F["price"](rows, 260, 120, True)
        self.assertEqual((fixed["serial_known_rows"], fixed["attempts"]), (2, 1))
        self.assertEqual(fixed["fractions"]["50"]["projected_ns"], 126)
        self.assertEqual(fixed["fractions"]["50"]["uniform_ns_per_attempt"], -6)
        callbacks = F["price"](rows, 260, 120, False)
        self.assertEqual(callbacks["fractions"]["0"]["projected_ns"], 108)
        self.assertEqual(callbacks["fractions"]["100"]["projected_ns"], 60)

    def test_return_envelope_and_all_layers_are_required(self):
        calls = [dict(number=i, enter_ns=100 * i, return_ns=100 * i + 80) for i in range(1, 4)]
        spans = [(i, 0, i * 100, i * 100 + 6) for i in (1, 2)]
        spans += [(3, layer, 300 + 2 * layer, 301 + 2 * layer) for layer in range(36)]
        actions = ["prefill", "prefill", "anchor"]
        self.assertEqual(F["decompose"](calls, actions, spans)[-1], ("anchor", 80, 30, 11))
        with self.assertRaises((ValueError, RuntimeError, AssertionError)):
            F["decompose"](calls, actions, spans[:-1])
