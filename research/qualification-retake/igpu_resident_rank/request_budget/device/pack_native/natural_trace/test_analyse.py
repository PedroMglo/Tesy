import json
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from analyse import GEOMETRY, HISTORICAL, bound, close_barrier, verify_routes


class HostChecks(unittest.TestCase):
    def test_consumer_wait(self):
        key = (25, 7, 3, 10)
        wake = SimpleNamespace(call=2, tile=1, layer=25, wave=1, ns=140, a=1)
        args = (wake, (2, 1, 25, 1), [key], {(25, 7): (key, 2)}, {key: 135}, (100, 1, [key]))
        counter = Counter()
        close_barrier(*args, counter)
        self.assertEqual(counter["wait_to_last_publication_ns"], 35)
        self.assertEqual(counter["last_publication_to_resume_ns"], 5)
        for k, v in [(3, {(25, 7): (key, 1)}), (4, {key: 150}), (5, (100, 0, [key]))]:
            with self.subTest(k=k), self.assertRaises(ValueError):
                broken = list(args)
                broken[k] = v
                close_barrier(*broken, Counter())

    def test_mask_and_demands(self):
        calls = [{"geometry": [(1, 2044, 2044)]}]
        ranks = {(1, 1, layer): [(3, 2, 1, 0)] for layer in range(35)}
        demands = {site: [0, 3, 1, 2] for site in ranks}
        masks = dict.fromkeys(ranks, 1)
        self.assertEqual(verify_routes(ranks, demands, masks, calls)["rows"], 35)
        for bad in ({**demands, (1, 1, 0): [3, 2, 1]}, {**demands, (1, 1, 2): [0, 3, 1, 2, 3]}):
            with self.assertRaises(ValueError):
                verify_routes(ranks, bad, masks, calls)
        with self.assertRaises(ValueError):
            verify_routes({**ranks, (1, 1, 35): [(0, 1, 2, 3)]}, demands, masks, calls)

    def test_scope_and_optimistic_deadline(self):
        ns = 10**9
        host = {
            "calls": [
                {"enter_ns": 2 * ns, "return_ns": 4 * ns},
                {"enter_ns": 5 * ns, "return_ns": 7 * ns},
            ],
            "callback_spans": [(1, 2 * ns, 3 * ns), (2, 5 * ns, 6 * ns)],
            "wait_spans": [(1, 2 * ns, 3 * ns)],
        }
        full = {
            "accepted": True,
            "timings": {
                "cache_n": 2044,
                "prompt_n": 153,
                "predicted_n": 47,
                "prompt_ms": 10000,
                "predicted_ms": 9000,
            },
            "stream_metrics": {"first_final_content_chunk_s": 18},
            "request_started_monotonic": 1,
            "request_ended_monotonic": 20.1,
        }
        res = bound(host, full, {"prefill_s": 10, "decode_s": 9, "first_final_s": 18})
        self.assertEqual(res["host_unions"]["callback_spans"]["prefill_ns"], 2 * ns)
        self.assertEqual(res["scenarios"]["6"]["decision"], "NO_GO_FIXED_EXTERIOR")
        self.assertEqual(res["independent_last_cuda_consumer"], "UNKNOWN")

    def test_reference(self):
        row = json.loads(Path(__file__).with_name("historical.json").read_bytes())
        self.assertEqual(row["journal_sha256"], HISTORICAL)
        self.assertEqual(row["route"]["rows"], 35 * (153 + 46) + 47)
        self.assertEqual(sum(map(sum, GEOMETRY)), 199)


if __name__ == "__main__":
    unittest.main()
