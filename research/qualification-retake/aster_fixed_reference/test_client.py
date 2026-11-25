"""The diagnostic answers a fixed input only after checking both tokenization conventions."""

import importlib.util
import json
import tempfile
import threading
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("fixed_aster_client", HERE / "client.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
from c2_server_run import parse_chat_stream  # noqa: E402


class Reference(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.raw = Path(d.name)
        self.probe = object.__new__(c.Probe)
        self.probe.messages = [
            {"role": "user", "content": "private prompt"},
            {"role": "assistant", "content": "private final"},
            {"role": "user", "content": "private followup"},
        ]
        self.probe.spec = {"required": ["Aster"]}
        self.probe.pins = {"synthetic": True}
        self.probe.official = list(range(435))
        self.probe.primer_ids = list(range(123))
        self.probe.turn_authority = {"messages_sha256": c.pair.digest(self.probe.messages)}
        self.status = {"http_requests_sent": 0, "sampling_tokens_requested": 0}
        self.chats = []
        self.flags = []
        self.owner = []

    def run_case(
        self,
        answer="Aster",
        *,
        reasoning="private thought",
        split=(122, 313),
        mutate=False,
        wrong_render=False,
        finish="stop",
        done=True,
        product_sec=600,
        pause=0,
        cap=7,
        primer_failure=False,
        missing_stats=False,
    ):
        def primer(pid, raw, cancelled, progress, ids, port, deadline, hsh):
            self.assertEqual((pid, port, hsh), (71, 1234, c.PRIMER))
            self.assertEqual(len(ids), 123)
            progress["http_requests_sent"] += 1
            progress["sampling_tokens_requested"] += 1
            if primer_failure:
                raise ValueError("private backend")
            return {"client_s": 0.01, "cache_n": 0, "prompt_n": 123, "predicted_n": 1}

        def fetch(path, data=None, **kwargs):
            if path == "/v1/models":
                return {"data": [{"id": "private-model-id"}]}
            if path == "/apply-template":
                self.assertEqual(data, c.pair.payload("private-model-id", self.probe.messages))
                return {"prompt": "different" if wrong_render else "private prompt"}
            self.flags.append(data["add_special"])
            ids = self.probe.official[:]
            if mutate and data["add_special"]:
                ids[-1] += 1
            return {"tokens": ids}

        def chat(body, remaining, start, base_url):
            self.chats.append(body)
            self.assertEqual((body["temperature"], body["seed"], body["max_tokens"]), (0, 42, 768))
            self.assertEqual(
                body["chat_template_kwargs"],
                {"tesy_template_date": "2026-09-29", "reasoning_effort": "medium"},
            )
            self.assertTrue(body["cache_prompt"] and remaining <= self.probe.timeout_s)

            def chunk(delta, stop=None):
                return {"choices": [{"delta": delta, "finish_reason": stop}]}

            clock = {
                "cache_n": split[0],
                "prompt_n": split[1],
                "predicted_n": cap,
                "prompt_ms": 35.5,
                "predicted_ms": 20.3,
                "predicted_per_second": 23,
            }
            usage = {
                "completion_tokens": cap,
                "prompt_tokens": 435,
                "total_tokens": 435 + cap,
                "prompt_tokens_details": {"cached_tokens": split[0]},
            }
            events = [
                chunk({"role": "assistant"}),
                chunk({"reasoning_content": reasoning}),
                chunk({"content": answer}),
                chunk({}, finish),
                {"choices": [], "usage": usage, **({} if missing_stats else {"timings": clock})},
            ]

            def lines():
                if pause:
                    time.sleep(pause)
                for obj in events:
                    line = "data: " + json.dumps(obj) + "\n"
                    c._REQUEST_LOCAL.evidence.write("SSE_FRAGMENT", fragment=line)
                    yield line
                if done:
                    yield "data: [DONE]\n"

            return parse_chat_stream(lines(), lambda: time.monotonic() - start)

        with ExitStack() as stack:
            for target, attr, value in (
                (c, "primer", primer),
                (c, "listener_port", lambda raw: 1234),
                (c, "RENDER", c.sha(b"private prompt")),
                (c, "PRODUCT_SECONDS", product_sec),
                (c.split, "owned_listener", lambda *a: self.owner.append(a)),
                (c.original, "stream_chat", chat),
                (c.original, "fetch", fetch),
            ):
                stack.enter_context(patch.object(target, attr, value))
            return self.probe.run(71, self.raw, threading.Event(), self.status)

    def test_one_primer_one_chat_positive(self):
        result = self.run_case(answer="ASTER")
        self.assertEqual(self.flags, [False, True])
        self.assertTrue(all(x == (71, 1234) for x in self.owner))
        self.assertEqual(result["counts"], (435, 122, 313))
        self.assertEqual(result["stock_T2_C132_grade"], "PASS")
        self.assertTrue(result["validated_within_600s"])
        self.assertEqual(result["natural_two_turn_session"], "NOT_RUN")
        self.assertEqual(self.status["sampling_tokens_requested"], 769)
        self.assertEqual(self.status["http_requests_sent"], 2)
        self.assertNotIn("private", json.dumps(result))
        self.assertTrue((self.raw / "T2-response.json").is_file())

    def test_absent_final_keeps_grade_fail_even_if_reasoning_contains_aster(self):
        result = self.run_case(answer="another final", reasoning="Aster")
        self.assertFalse(result["Aster_in_final_casefold"])
        self.assertEqual(result["content_contrast"], "BOTH_OMIT_ASTER_ON_FIXED_HISTORY")
        self.assertEqual(result["stock_T2_C132_grade"], "FAIL")

    def test_product_censor_continues_same_single_chat(self):
        result = self.run_case(answer="Aster", product_sec=0.008, pause=0.03)
        self.assertTrue((self.raw / "T2-product-censor.json").is_file())
        self.assertFalse(result["validated_within_600s"])
        self.assertTrue(result["Aster_in_final_casefold"])
        self.assertEqual(len(self.chats), 1)
        self.assertEqual(
            result["C133_clock_observation"], "CENSORED_AT_600S_DIAGNOSTIC_CONTINUATION"
        )

    def test_mismatch_add_special_prevents_chat(self):
        with self.assertRaisesRegex(c.Gate, "official_ID"):
            self.run_case(mutate=True)
        self.assertEqual(self.status["http_requests_sent"], 1)
        self.assertFalse(self.chats)

    def test_prior_primer_failure_does_not_send_chat(self):
        with self.assertRaises(c.Gate):
            self.run_case(primer_failure=True)
        self.assertFalse(self.chats)
        self.assertNotIn("private backend", (self.raw / "fixed-reference-failure.json").read_text())

    def test_render_mismatch_does_not_start_chat(self):
        with self.assertRaisesRegex(c.Gate, "render"):
            self.run_case(wrong_render=True)
        self.assertFalse(self.flags)

    def test_compensating_cache_and_prompt_mismatch_fails(self):
        with self.assertRaisesRegex(c.Gate, "split"):
            self.run_case(split=(123, 312))
        self.assertTrue((self.raw / "T2-response.json").is_file())

    def test_missing_done_fails(self):
        with self.assertRaises(c.Gate):
            self.run_case(done=False)
        self.assertTrue((self.raw / "T2-request.jsonl").is_file())

    def test_missing_stats_fails(self):
        with self.assertRaises(c.Gate):
            self.run_case(missing_stats=True)

    def test_output_cap_not_natural(self):
        with self.assertRaises(c.Gate):
            self.run_case(cap=768, finish="length")

    def test_timing_equality_is_censored_and_order_consistent(self):
        self.assertFalse(c.comparison(True, True, 599.99, 600)["validated_within_600s"])
        with self.assertRaises(c.Gate):
            c.comparison(True, True, 600, 599.99)


if __name__ == "__main__":
    unittest.main()
