"""Model-free checks of the full-cache parser, dated example and single probe lifecycle."""

import argparse
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
    def test_E20_requires_probe_opt_in_matching_scope_and_full_C55_margin(self):
        class LargeProbe:
            run_id = "test-aster-e20-ram"
            pass_status = "PASS_TEST"
            timeout_s = 2
            ram_profile = "R0_E20"

        class Undeclared(LargeProbe):
            pass

        class Invalid(LargeProbe):
            ram_profile = "R0_E22"

        profile = loader.Profile(LargeProbe())
        self.assertEqual(loader.Profile().paging_cap_bytes, 10 * loader.start.GIB)
        self.assertEqual(loader.Profile(Undeclared()).paging_cap_bytes, 10 * loader.start.GIB)
        with self.assertRaisesRegex(ValueError, "unknown_stock_ram_profile"):
            loader.Profile(Invalid())
        lock = loader.ROOT / "results/post-c195-epoch-20260930T223734Z/resource-policy.json"
        policy = loader.start.read(lock)
        requested = loader.start.cap_for(policy, paging=True, ready_profile=profile)
        self.assertEqual(requested, 21474836480)
        resource = loader.start.policy_api.freeze_protocol_resource_limits(
            policy,
            cgroup_memory_max_bytes=requested,
            start_mode="CAPACITY_ADMISSION_START",
            execution_class="FILE_PAGING",
        )
        guard = loader.start.policy_api.validate_resource_protocol(
            {"resources": resource, "limits": {}}
        )
        self.assertEqual(guard["cgroup"]["memory_high_bytes"], 20937965568)
        self.assertEqual(guard["memory"]["reserve_bytes"], 2 * loader.start.GIB)
        memory = policy["memory"]
        window = {
            "status": "PASS_RESOURCE_WINDOW_ONLY",
            "reason": [],
            "canonical_memory": memory,
            "memory": memory,
        }
        profile.admit_memory(window, policy)
        for key, bad in (
            ("cap_max_bytes", requested - 1),
            ("available_min_bytes", requested + memory["reserve_bytes"] - 1),
            ("reserve_bytes", 2 * loader.start.GIB - 1),
        ):
            for source in ("canonical_memory", "memory"):
                with (
                    self.subTest(key=key, source=source),
                    self.assertRaisesRegex(ValueError, "C55_"),
                ):
                    profile.admit_memory(window | {source: memory | {key: bad}}, policy)
        with self.assertRaisesRegex(ValueError, "C55_E20_host_reserve_or_window"):
            profile.admit_memory(
                window | {"status": "NOT_ADMITTED", "reason": ["C55_CAP_UNAVAILABLE"]}, policy
            )
        # A genuinely admissible C55 cannot silently run E20 inside an E10 cgroup.
        scope = {
            "memory_max": 10 * loader.start.GIB,
            "memory_high": int(9.5 * loader.start.GIB),
            "swap_max": 0,
            "swap_current": 0,
        }
        with (
            TemporaryDirectory() as tmp,
            patch.object(loader.start.bounded, "cgroup_state", return_value=scope),
            patch.object(loader.start.subprocess, "Popen") as spawn,
        ):
            a = argparse.Namespace(
                new_raw=Path(tmp) / "raw", new_output=Path(tmp) / "result", policy=lock
            )
            self.assertEqual(
                loader.start.run(a, paging=True, placement_log=True, ready_profile=profile),
                "NOT_RUN",
            )
            self.assertEqual(
                loader.start.read(a.new_output / "receipt.json")["reason"], "scope_limit"
            )
            spawn.assert_not_called()

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
