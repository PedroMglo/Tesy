"""Without a model, exercise the frozen product grader, stock SSE shape and stop gates."""

import io
import json
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import client


def event(**obj):
    return b"data: " + json.dumps(obj).encode() + b"\n\n"


def stream(answer, length, cache, finish="stop"):
    def chunk(delta, stop=None):
        return event(choices=[{"delta": delta, "finish_reason": stop}])

    usage = {
        "completion_tokens": 3,
        "prompt_tokens": length,
        "total_tokens": length + 3,
        "prompt_tokens_details": {"cached_tokens": cache},
    }
    t = {
        "cache_n": cache,
        "prompt_n": length - cache,
        "predicted_n": 3,
        "prompt_ms": 15.0,
        "predicted_ms": 303.0,
        "predicted_per_second": 9.90,
    }
    return (
        chunk({"role": "assistant", "content": None})
        + chunk({"reasoning_content": "private analysis"})
        + chunk({"content": answer})
        + chunk({}, finish)
        + event(choices=[], usage=usage, timings=t)
        + b"data: [DONE]\n\n"
    )


class FakeHTTP:
    def __init__(self, reply):
        self.reply = io.BytesIO(reply)
        self.reply.status = 200
        self.reply.getheader = lambda *args: "text/event-stream; charset=utf-8"
        self.sock = MagicMock()
        self.request_body = None

    def request(self, method, path, body, headers):
        assert (method, path) == ("POST", "/v1/chat/completions")
        self.request_body = json.loads(body)

    def getresponse(self):
        return self.reply

    def connect(self):
        pass

    def close(self):
        self.reply.close()


class Gates(unittest.TestCase):
    def setUp(self):
        self.probe = object.__new__(client.Probe)
        usr = [{"role": "user", "content": "private user"}]
        history = usr + [
            {"role": "assistant", "content": "12345"},
            {"role": "user", "content": "private followup"},
        ]
        self.probe.tasks = [
            {"messages": usr, "timeout_s": 180},
            {"messages": history[-1:], "timeout_s": 90},
        ]
        self.probe.references = [
            {"messages": usr, "official_ids": [1] * 2043, "rendered_prompt": "private T1"},
            {
                "messages": history,
                "official_ids": [1] * 2043 + [2] * 154,
                "rendered_prompt": (
                    "private <|start|>assistant<|channel|>final<|message|>12345<|end|> suffix"
                ),
            },
        ]
        self.progress = {"http_requests_sent": 0, "sampling_tokens_requested": 0}
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.raw = Path(self.directory.name)
        self.auth, self.bodies = [], []

    def exercise(
        self,
        first="12345",
        second="12345",
        cache=2044,
        mutate_ids=False,
        raw_t1=None,
        finish="stop",
        cancel_before=False,
    ):
        refs = self.probe.references
        dates = []
        inputs = []

        def fetch(path, data, **kwargs):
            if path == "/v1/models":
                return {"data": [{"id": "model"}]}
            if path == "/apply-template":
                dates.append(data["chat_template_kwargs"])
                turn = len(dates)
                prompt = client.expected_render(turn, refs[turn - 1], data["messages"])
                inputs.append(data["messages"])
                return {"prompt": prompt}
            turn = len(dates)
            ids = refs[turn - 1]["official_ids"][:]
            if mutate_ids or (turn == 2 and first != "12345"):
                ids[-1] = 3
            return {"tokens": ids}

        replies = [
            raw_t1 if raw_t1 is not None else stream(first, 2043, 0, finish),
            stream(second, 2197, cache),
        ]

        def http(*args, **kwargs):
            obj = FakeHTTP(replies[len(self.bodies)])
            self.bodies.append(obj)
            return obj

        with ExitStack() as stack:
            stack.enter_context(patch.object(client.original, "fetch", fetch))
            stack.enter_context(patch.object(client, "listener_port", return_value=18442))
            stack.enter_context(
                patch.object(
                    client, "owned_listener", side_effect=lambda *args: self.auth.append(args)
                )
            )
            stack.enter_context(
                patch.object(client.http.client, "HTTPConnection", side_effect=http)
            )
            cancelled = threading.Event()
            if cancel_before:
                cancelled.set()
            result = self.probe.run(123, self.raw, cancelled, self.progress)
        self.assertEqual(dates, [client.KWARGS] * 2)
        self.assertEqual(inputs[1][1], {"role": "assistant", "content": first})
        return result

    def test_real_parser_two_turns_and_public_privacy(self):
        result = self.exercise()
        self.assertEqual(
            (result["completed_turns"], self.progress["sampling_tokens_requested"]), (2, 512)
        )
        row = result["rows"][1]
        self.assertEqual(row["paired_nominal_input"], "MATCHED_IDS_AND_SPLIT")
        self.assertTrue(row["nominal_first_final_le_10s"] and row["nominal_decode_ge_6"])
        self.assertGreaterEqual(row["first_final_s"], row["first_reasoning_s"])
        self.assertGreaterEqual(row["validated_terminal_s"], row["transport_complete_s"])
        self.assertEqual(row["output_ids_authority"], "NOT_EXPOSED_EMPTY_OR_ABSENT")
        self.assertEqual(self.bodies[1].request_body["max_tokens"], 256)
        self.assertEqual(self.bodies[1].request_body["seed"], 42)
        self.assertNotIn("private", json.dumps(result))
        self.assertNotIn("12345", json.dumps(result))
        self.assertEqual(self.auth, [(123, 18442)] * 7)

    def test_distinct_own_history_valid_product(self):
        result = self.exercise("54321", "54321")
        row = result["rows"][1]
        self.assertTrue(row["accepted"])
        self.assertEqual(row["paired_nominal_input"], "INCONCLUSIVE")
        self.assertIsNone(row["nominal_first_final_le_10s"])

    def test_changed_live_split_has_no_nominal_verdict(self):
        row = self.exercise(cache=2043)["rows"][1]
        self.assertTrue(row["accepted"])
        self.assertEqual(row["paired_nominal_input"], "INCONCLUSIVE")
        self.assertIsNone(row["nominal_decode_ge_6"])

    def test_foreign_ids_stop_before_first_request(self):
        with self.assertRaisesRegex(client.Gate, "official_ids"):
            self.exercise(mutate_ids=True)
        self.assertEqual(self.progress["http_requests_sent"], 0)

    def test_invalid_first_content_preserves_failure_and_no_followup(self):
        with self.assertRaisesRegex(client.Gate, "content_gate_failed"):
            self.exercise(first="x")
        self.assertEqual(self.progress["http_requests_sent"], 1)
        failure = json.loads((self.raw / "product-failure.json").read_bytes())
        self.assertEqual(
            (failure["completed_turns"], failure["rows"][0]["content_gate"]), (0, "FAIL")
        )
        self.assertFalse((self.raw / "T2-input.json").exists())

    def test_rejected_capped_or_unfinished_first_stops(self):
        with self.assertRaises(client.Gate):
            self.exercise(finish="length")
        self.assertEqual(self.progress["http_requests_sent"], 1)

    def test_missing_usage_retains_stream_progress_and_no_followup(self):
        data = stream("12345", 2043, 0).split(b'data: {"choices": []')[0] + b"data: [DONE]\n\n"
        with self.assertRaises(client.Gate):
            self.exercise(raw_t1=data)
        self.assertIsNotNone(self.progress["product_progress"]["first_final_s"])
        self.assertTrue((self.raw / "T1-request.jsonl").is_file())
        self.assertEqual(self.progress["http_requests_sent"], 1)

    def test_timeout_uses_wall_clock_and_no_followup(self):
        self.probe.tasks[0]["timeout_s"] = 0
        with self.assertRaisesRegex(client.Gate, "PER_REQUEST_WALL_TIMEOUT"):
            self.exercise()
        self.assertLessEqual(self.progress["http_requests_sent"], 1)
        self.assertIsNone(self.progress["product_progress"]["first_final_s"])

    def test_cancel_stops_before_post(self):
        with self.assertRaisesRegex(client.Gate, "monitor_cancelled"):
            self.exercise(cancel_before=True)
        self.assertEqual(self.progress["http_requests_sent"], 0)

    def test_changed_harmony_framing_of_own_answer_rejected(self):
        ref = self.probe.references[1]
        with self.assertRaisesRegex(client.Gate, "live_render_differs"):
            client.check_input(
                2, ref, ref["messages"], ref["rendered_prompt"] + " ", ref["official_ids"]
            )


if __name__ == "__main__":
    unittest.main()
