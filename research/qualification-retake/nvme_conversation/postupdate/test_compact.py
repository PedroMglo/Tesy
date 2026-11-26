import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "c281_driver_compaction", Path(__file__).with_name("compact.py")
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
request_status, sha, summarize = module.request_status, module.sha, module.summarize


class ClosedSession(unittest.TestCase):
    def test_no_terminal_no_read_of_raws(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            with self.assertRaisesRegex(ValueError, "unclosed"):
                summarize(root, root, "123")

    def test_failed_zero_launch_without_private_error(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            p = root / "receipt.json"
            p.write_text(
                json.dumps(
                    {
                        "status": "FAIL_PRESERVED",
                        "failure": "private value",
                        "model_launches": 0,
                        "envelope_s": 0.25,
                    }
                )
            )
            result = summarize(root, root, sha(p))
            self.assertEqual(
                (
                    result["requests_started"],
                    result["requests_accepted"],
                    result["responses_with_sse"],
                ),
                (0, 0, 0),
            )
            self.assertNotIn("private value", json.dumps(result))

    def test_journal_before_post_is_not_network_or_content(self):
        with tempfile.TemporaryDirectory() as name:
            raw = Path(name)
            journal = raw / "T1-request.jsonl"
            journal.write_text(
                json.dumps(dict(kind="REQUEST_START", monotonic_s=3))
                + "\n"
                + json.dumps(dict(kind="REQUEST_TERMINAL", accepted=False, monotonic_s=4))
                + "\n"
            )
            one, two = request_status(raw)
            self.assertTrue(one["request_started"])
            self.assertFalse(one["received_sse"])
            self.assertFalse(one["accepted"])
            self.assertFalse(two["request_started"])


if __name__ == "__main__":
    unittest.main()
