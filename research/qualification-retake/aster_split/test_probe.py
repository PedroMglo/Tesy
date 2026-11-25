import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe import Probe, validated_counts


class CacheProbeTests(unittest.TestCase):
    def test_new_tokens_and_claims_must_match_server(self):
        result = {
            "id_slot": 0,
            "tokens_predicted": 1,
            "tokens_evaluated": 435,
            "stop": True,
            "truncated": False,
            "tokens": [1234],
            "timings": {
                "cache_n": 122,
                "prompt_n": 313,
                "predicted_n": 1,
                "prompt_ms": 12.25,
                "predicted_ms": 0,
            },
        }
        self.assertEqual(validated_counts(result, 435, 122)["prompt_n"], 313)
        for mutation in (
            {"cache_n": 0, "prompt_n": 435},
            {"prompt_n": 312},
            {"predicted_n": True},
            {"prompt_ms": float("nan")},
        ):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validated_counts(result | {"timings": result["timings"] | mutation}, 435, 122)

    def test_preserves_one_failed_exchange_and_stops_before_second_request(self):
        gate = object.__new__(Probe)
        gate.prompts = [[2] * 123, [2] * 435]
        connection = MagicMock()
        response = connection.getresponse.return_value
        response.status = 400
        response.read.return_value = b'{"error":"fixture"}'
        progress = {"http_requests_sent": 0}
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory)
            (raw / "server.log").write_text("listening on http://127.0.0.1:12345\n")
            with patch("probe.owned_listener") as owner:
                with patch("probe.http.client.HTTPConnection", return_value=connection):
                    with self.assertRaisesRegex(ValueError, "HTTP"):
                        gate.run(100, raw, threading.Event(), progress)
            owner.assert_called_once_with(100, 12345)
            connection.close.assert_called_once()
            self.assertEqual(progress["http_requests_sent"], 1)
            self.assertEqual(json.loads((raw / "exchange-1.json").read_bytes())["http_status"], 400)
            self.assertFalse((raw / "request-2.json").exists())


if __name__ == "__main__":
    unittest.main()
