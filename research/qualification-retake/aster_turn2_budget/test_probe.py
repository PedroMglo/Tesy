import json
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import probe


def raw(n=8, omitted=()):
    events = []
    for i in range(1, n + 1):
        row = dict(
            stop=False,
            tokens=[16 + i],
            tokens_predicted=i,
            tokens_evaluated=435,
            timings=dict(
                cache_n=122,
                prompt_n=313,
                predicted_n=i,
                prompt_ms=5000.0,
                predicted_ms=250.0 + (i - 1) * 1000,
            ),
        )
        if i not in omitted:
            events.append(row)
    events.append(
        {
            **row,
            "stop": True,
            "tokens": [],
            "stop_type": "limit" if n == 8 else "eos",
            "id_slot": 0,
            "truncated": False,
        }
    )
    return b"".join(b"data: " + json.dumps(v).encode() + b"\n\n" for v in events)


class Budget(unittest.TestCase):
    def test_calibration_includes_first_token_and_primer_exactly_once(self):
        obs, _, steps = probe.budget.trajectory(raw(), 14.0, 435, 122)
        result = probe.project(obs, steps, 70.0)
        self.assertEqual(result["first_endpoint_s"], 0.25)
        self.assertEqual(result["estimated_fixed_s"], 77.0)
        self.assertEqual(result["projected_historical_s"]["mean"], 528.0)
        self.assertEqual(result["projected_cap768_s"]["mean"], 844.0)
        self.assertEqual(result["decision"], "GO_FIXTURE_FIXED_T2_ONLY")

    def test_three_prospective_outcomes(self):
        def evaluate(steps):
            obs = dict(
                client_wall_s=100 + sum(steps),
                server_prompt_s=100.0,
                server_generation_s=sum(steps),
            )
            return probe.project(obs, steps, 100.0)["decision"]

        self.assertEqual(evaluate([5.0] * 7), "NO_GO_FIXED_T2_BUDGET")
        self.assertEqual(evaluate([1.0, 5.0, 1.0, 2.0, 3.0, 3.0, 2.0]), "INCONCLUSIVE_BUDGET")
        self.assertEqual(evaluate([2.0] * 7), "GO_FIXTURE_FIXED_T2_ONLY")

    def test_authenticated_first_id_or_stop(self):
        instance = object.__new__(probe.Probe)
        instance.primer_hash = "sha"
        instance.t2_hash = "sha"
        instance.prompts = ([9] * 123, [8] * 435)
        instance.first_id = 17

        def observe(data):
            with (
                patch.object(probe.budget, "listener_port", return_value=9),
                patch.object(probe, "primer", return_value={"client_s": 70}),
                patch.object(probe.budget, "exchange", return_value=(data, 14.0, "sha")),
            ):
                return instance.run(1, Path("."), threading.Event(), {})

        self.assertTrue(observe(raw())["first_T2_id_matches_split"])
        self.assertEqual(observe(raw(3))["decision"], "INCONCLUSIVE_EARLY_STOP")
        self.assertEqual(
            observe(raw(8, omitted=(4,)))["decision"], "INCONCLUSIVE_MISSING_TOKEN_CLOCK"
        )
        instance.first_id = 314
        with self.assertRaisesRegex(ValueError, "first ID"):
            observe(raw())


if __name__ == "__main__":
    unittest.main()
