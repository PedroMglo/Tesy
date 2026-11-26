import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from runpy import run_path

R = run_path(Path(__file__).with_name("review.py"))


class TransportTests(unittest.TestCase):
    def test_projection_preserves_nonvolatile_verbose_fields(self):
        frame = {
            "id": "a",
            "created": 1,
            "timings": {"ms": 2},
            "__verbose": {"prompt": "local", "timings": {"ms": 2}},
            "choices": [{"delta": {"content": "x"}}],
        }
        actual = R["stable_frame"](frame)
        changed = frame | {
            "id": "b",
            "created": 2,
            "timings": {"ms": 3},
            "__verbose": {"prompt": "local", "timings": {"ms": 3}},
        }
        self.assertEqual(R["stable_frame"](changed), actual)
        self.assertNotEqual(R["stable_frame"](changed | {"__verbose": {"prompt": "other"}}), actual)
        self.assertNotEqual(R["stable_frame"](changed | {"choices": []}), actual)

    def test_shutdown_window_if_process_exits_within_killpg_interval(self):
        marks = dict(
            sigint_before_ns=20,
            sigint_after_ns=30,
            pidfd_exit_observed_ns=25,
            server_port_scope_verified_ns=80,
        )
        result = R["shutdown_clock"](10, marks)
        self.assertEqual(result["sigint_to_pidfd_observation_lower_s"], 0)
        self.assertEqual(result["sigint_to_pidfd_observation_upper_s"], 5e-9)
        self.assertEqual(result["post_client_to_verified_cleanup_s"], 70e-9)
        with self.assertRaises(ValueError):
            R["shutdown_clock"](10, marks | {"pidfd_exit_observed_ns": 15})

    @unittest.skipUnless(
        os.getenv("TESY_REVIEW_IDS_FIXTURE") and os.getenv("TESY_REVIEW_HISTORY"),
        "optional authenticated historical capture",
    )
    def test_closed_fixture_and_counterexamples(self):
        sample = Path(os.environ["TESY_REVIEW_IDS_FIXTURE"])
        gold = Path(os.environ["TESY_REVIEW_HISTORY"])
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "sample"
            shutil.copytree(sample, dst)
            receipt = R["read"](dst / "receipt.json")
            result = R["grade_arm"](dst, receipt, gold)
            self.assertEqual(result["transport"]["mode"], "HISTORICAL_FIXTURE_ONLY")
            self.assertEqual([r["feed_echoes"] for r in result["rows"]], [77, 46])
            self.assertTrue(
                all(r["transport_complete_s"] < r["validated_terminal_s"] for r in result["rows"])
            )
            # Exchange a parser timestamp for a real earlier event outside its content frame.
            raw = dst / "raw"
            full = R["read"](raw / "T2-result.json")
            full["stream_metrics"]["first_final_content_chunk_s"] = full["stream_metrics"][
                "first_text_chunk_s"
            ]
            with self.assertRaisesRegex(ValueError, "actual SSE frame"):
                R["compare_transport"](raw, gold, 2, full, R["native"].GEOMETRY[1])
            # A metadata-only mutation does not change choices/usage; the full frame grade rejects.
            path = raw / "T2-request.jsonl"
            journal = R["lines"](path)
            for row in journal:
                if row.get("kind") == "SSE_FRAGMENT" and row["fragment"].startswith("data: {"):
                    f = json.loads(row["fragment"][6:])
                    f["model"] = "different"
                    row["fragment"] = "data: " + json.dumps(f) + "\n"
                    break
            path.write_text("".join(json.dumps(r) + "\n" for r in journal))
            with self.assertRaisesRegex(ValueError, "complete stable SSE"):
                R["grade_arm"](dst, receipt, gold)


if __name__ == "__main__":
    unittest.main()
