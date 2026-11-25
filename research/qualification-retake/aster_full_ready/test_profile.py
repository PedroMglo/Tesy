"""Model-free checks of the full-cache parser, dated example and single probe lifecycle."""

import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import loader

JOURNAL = """CPU_Mapped model buffer size = 2 MiB
llama_kv_cache_iswa: using full-size SWA cache (ref: ...)
llama_kv_cache_iswa: creating non-SWA KV cache, size = 8192 cells
llama_kv_cache: CUDA0 KV buffer size =   288.00 MiB
llama_kv_cache_iswa: creating     SWA KV cache, size = 8192 cells
llama_kv_cache: CUDA0 KV buffer size =   288.00 MiB
CUDA0 MoE cache size = 2042.30 MiB for 58092.19 MiB of host experts, 0% of the misses on the CPU
impl: 36 layers, mxfp4:   161 slots (3.5%, 1.1 tokens worth)
srv load_model: initializing, n_slots = 1, n_ctx_slot = 8192, kv_unified = 'false'
srv init: init: chat template, example_format: 'system
Current date: 2026-09-29
sample'
srv server_run_i: model loaded
srv server_on_li: listening on http://127.0.0.1:19433
"""


class ProfileTests(unittest.TestCase):
    def test_full_geometry_requires_both_caches_and_a_dated_server_example(self):
        self.assertTrue(all(loader.geometry(JOURNAL).values()))
        for before, after in (
            ("     SWA KV cache, size = 8192", "     SWA KV cache, size = 256"),
            ("288.00 MiB", "9.00 MiB"),
            ("161 slots", "160 slots"),
            ("0% of the misses", "10% of the misses"),
            ("n_slots = 1", "n_slots = 2"),
            ("2026-09-29", "2026-11-25"),
            ("model loaded", "listening"),
            ("127.0.0.1:19433", "0.0.0.0:19433"),
            ("using full-size SWA cache", "compact"),
        ):
            with self.subTest(before=before):
                self.assertFalse(all(loader.geometry(JOURNAL.replace(before, after)).values()))
        extra = JOURNAL.replace("2026-09-29", "wrong") + "\nCurrent date: 2026-09-29\n"
        self.assertFalse(loader.geometry(extra)["dated_init_example"])
        self.assertFalse(loader.geometry(JOURNAL + JOURNAL)["full_kv"])
        self.assertFalse(loader.start.logged_geometry(JOURNAL)["swa_kv"])

    def test_unknown_jinja_fails_before_any_parent_scope(self):
        with self.assertRaisesRegex(ValueError, "unknown_original"):
            loader.fixed_template(b"fake")

    def test_no_http_until_ready_gates_pass_and_a_probe_is_present(self):
        release = threading.Event()
        cancelled = threading.Event()

        class Probe:
            run_id = "test-model-free-probe"
            pass_status = "PASS_PROBE_ONLY"
            timeout_s = 2

            def run(self, pid, raw, cancelled, progress):
                release.wait(1)
                progress.update(http_requests_sent=2, sampling_tokens_requested=2)
                return {"valid": True}

        with TemporaryDirectory() as tmp:
            profile = loader.Profile(Probe())
            raw = Path(tmp)
            (raw / loader.TEMPLATE).write_bytes(b"invalid")
            with self.assertRaisesRegex(ValueError, "template_changed"):
                profile.at_ready(1, raw, cancelled, [])
            self.assertFalse(profile.probe_started)
            with patch.object(loader.Profile, "verify_template"):
                offline = loader.Profile()
                self.assertIsNone(offline.at_ready(1, raw, cancelled, []))
                self.assertFalse(offline.probe_started)
                self.assertIsNone(profile.at_ready(1, raw, cancelled, ["live_elf_or_gguf"]))
                self.assertFalse(profile.probe_started)
                self.assertIsNotNone(profile.at_ready(1, raw, cancelled, []))
            record = {}
            self.assertFalse(profile.probe_finished(record))
            release.set()
            profile.thread.join(1)
            self.assertTrue(profile.probe_finished(record))
            profile.close(record)
            self.assertEqual(
                record,
                {
                    "after_ready": {"valid": True},
                    "http_requests_sent": 2,
                    "sampling_tokens_requested": 2,
                },
            )

    def test_probe_counts_attempts_and_preserves_the_first_failure(self):
        class Probe:
            run_id = "faulty-model-free-probe"
            pass_status = "PASS_TEST_ONLY"
            timeout_s = 1

            def run(self, pid, raw, cancelled, progress):
                progress["http_requests_sent"] += 1
                progress["sampling_tokens_requested"] += 1
                raise ValueError("test_missing_split")

        profile = loader.Profile(Probe())
        self.assertFalse(loader.Profile().probe_started)
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaisesRegex(ValueError, "invalid_probe_start"):
            profile.launch_probe(1, Path("."), cancelled)
        cancelled.clear()
        profile.launch_probe(1, Path("."), cancelled)
        profile.thread.join(1)
        with self.assertRaisesRegex(ValueError, "test_missing_split"):
            profile.probe_finished({})
        with self.assertRaisesRegex(ValueError, "invalid_probe_start"):
            profile.launch_probe(1, Path("."), cancelled)
        record = {}
        profile.close(record)
        self.assertEqual(record["http_requests_sent"], 1)
        self.assertEqual(record["sampling_tokens_requested"], 1)


if __name__ == "__main__":
    unittest.main()
