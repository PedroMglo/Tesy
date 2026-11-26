import json
import runpy
import unittest
from pathlib import Path

budget = runpy.run_path(str(Path(__file__).with_name("probe.py")))


def wire(n=8, step=1, omitted=(), terminal=True):
    rows = []
    for i in range(1, n + 1):
        t = {
            "predicted_n": i,
            "prompt_n": 121,
            "cache_n": 0,
            "prompt_ms": 80000.0,
            "predicted_ms": float(max(0.001, (i - 1) * step * 1000)),
        }
        obj = {
            "stop": False,
            "tokens": [17],
            "tokens_evaluated": 121,
            "tokens_predicted": i,
            "timings": t,
        }
        if i not in omitted:
            rows.append(obj)
    if terminal:
        rows.append(
            obj
            | {
                "stop": True,
                "truncated": False,
                "id_slot": 0,
                "tokens": [],
                "stop_type": "limit" if n == 8 else "eos",
            }
        )
    return b"".join(b"data: " + json.dumps(row).encode() + b"\n\n" for row in rows)


class Budget(unittest.TestCase):
    def call(self, *args, **kw):
        return budget["parse"](
            wire(*args, **kw), 100, {"prompt_ms": 225000, "client_s": 225.01, "predicted_ms": 0.001}
        )

    def test_seven_intervals(self):
        out = self.call()
        self.assertEqual(out["decision"], "GO_CONSIDER_BOUNDED_PAIR")
        self.assertEqual(len(out["step_s"]), 7)
        self.assertEqual(self.call(step=4)["decision"], "NO_GO_STOCK_REFERENCE_BUDGET")

    def test_early_eos_or_missing_clock(self):
        self.assertEqual(self.call(n=3)["decision"], "INCONCLUSIVE_EARLY_STOP")
        self.assertEqual(self.call(omitted=(3,))["decision"], "INCONCLUSIVE_MISSING_TOKEN_CLOCK")

    def test_incomplete_response_cannot_qualify(self):
        with self.assertRaisesRegex(ValueError, "missing native stop"):
            self.call(terminal=False)


if __name__ == "__main__":
    unittest.main()
