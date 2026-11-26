import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aster_ram_budget import probe  # noqa: E402


def stream(length, cache, ids, step=1, omit=()):
    rows = []
    for index, token in enumerate(ids, 1):
        event = {
            "stop": False,
            "tokens": [token],
            "tokens_evaluated": length,
            "tokens_predicted": index,
            "timings": {
                "predicted_n": index,
                "prompt_n": length - cache,
                "cache_n": cache,
                "prompt_ms": 1000,
                "predicted_ms": max(0.001, (index - 1) * step * 1000),
            },
        }
        if index not in omit:
            rows.append(event)
    rows.append(
        event
        | {
            "stop": True,
            "id_slot": 0,
            "tokens": [],
            "truncated": False,
            "stop_type": "limit" if len(ids) == 8 else "eos",
        }
    )
    return b"".join(b"data: " + json.dumps(row).encode() + b"\n\n" for row in rows)


class DualContext(unittest.TestCase):
    def setUp(self):
        self.target = object.__new__(probe.Probe)
        first = list(range(121))
        self.generated = list(range(500, 508))
        self.target.prompts = [first, first + self.generated[:1] + [42] * 313]
        self.target.e10_ordered = probe.digest(list(enumerate(self.generated, 1)))
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.raw = Path(directory.name)
        (self.raw / "server.log").write_text("listening on http://127.0.0.1:9876")
        self.t1 = stream(121, 0, self.generated)
        self.t2 = stream(435, 122, self.generated, step=2)

    def measure(self, *streams):
        with patch.object(
            probe.budget, "exchange", side_effect=[(s, 15, "a" * 64) for s in streams]
        ) as exchange:
            self.exchange = exchange
            return self.target.run(90, self.raw, threading.Event(), {})

    def test_two_separate_contexts(self):
        out = self.measure(self.t1, self.t2)
        self.assertEqual(self.exchange.call_count, 2)
        self.assertEqual(out["requests"][0]["lcp_after_seven_and_eight"], [122, 122])
        self.assertEqual(out["requests"][1]["prompt_n"], 313)
        self.assertEqual(out["historical_nonfirst_steps"], [340, 451])
        self.assertAlmostEqual(
            out["projected_historical_s"]["unfavorable"], out["estimated_fixed_s"] + 340 + 451 * 2
        )
        self.assertEqual(out["decision"], "GO_CONSIDER_BOUNDED_PAIR")
        self.assertNotIn("generated", out["requests"][0])

    def test_digest_mismatch_stops_after_first(self):
        ids = self.generated[:]
        ids[3], ids[4] = ids[4], ids[3]
        with self.assertRaisesRegex(ValueError, "ordered IDs"):
            self.measure(stream(121, 0, ids), self.t2)
        self.assertEqual(self.exchange.call_count, 1)
        self.assertTrue((self.raw / "turn-1-observation.json").is_file())

    def test_prefix_mismatch_prevents_second(self):
        self.target.prompts[1][122] = self.generated[1]
        with self.assertRaisesRegex(ValueError, "prefix"):
            self.measure(self.t1, self.t2)
        self.assertEqual(self.exchange.call_count, 1)

    def test_wrong_split_fails(self):
        with self.assertRaisesRegex(ValueError, "wrong per-token timings"):
            self.measure(self.t1, stream(435, 121, self.generated))

    def test_early_endpoint_cannot_project(self):
        r = self.measure(stream(121, 0, self.generated[:3]), self.t2)
        self.assertEqual(self.exchange.call_count, 1)
        self.assertEqual(r["decision"], "INCONCLUSIVE_EARLY_STOP")
        self.assertIsNone(r["projected_historical_s"])

    def test_gap_in_second_clock_cannot_project(self):
        r = self.measure(self.t1, stream(435, 122, self.generated, omit=(3,)))
        self.assertEqual(r["decision"], "INCONCLUSIVE_MISSING_TOKEN_CLOCK")
        self.assertIsNone(r["projected_historical_s"])

    def test_slow_and_crossing_scenarios(self):
        def row(steps):
            return {"step_s": steps, "server_prompt_s": 150, "client_overhead_s": 0}

        self.assertEqual(
            probe.projection([row([2] * 7), row([3] * 7)])["decision"],
            "NO_GO_STOCK_REFERENCE_BUDGET",
        )
        self.assertEqual(
            probe.projection([row([1] * 7), row([1, 4, 1, 4, 1, 4, 1])])["decision"],
            "INCONCLUSIVE_BUDGET",
        )


if __name__ == "__main__":
    unittest.main()
