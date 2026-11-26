import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review  # noqa: E402


class ReviewTest(unittest.TestCase):
    def test_native_stop_and_unsynchronized_clocks(self):
        text = "PHASE load_begin 4\nPHASE load_end 9\nPHASE context_begin 15\n"
        r = review.phases(text, None, False, 2)
        self.assertEqual(r["native_intervals"]["load"]["seconds"], 5e-9)
        self.assertEqual(r["native_intervals"]["context"]["state"], "CENSORED")
        self.assertIsNone(r["native_intervals"]["context"]["seconds"])
        self.assertIsNone(r["supervisor_cleanup_s"])
        closed = review.phases(
            text + "PHASE cleanup_begin 20\nPHASE cleanup_end 40\n", None, False, 2
        )
        self.assertEqual(closed["native_intervals"]["cleanup"]["seconds"], 20e-9)
        with self.assertRaises(ValueError):
            review.phases(text + "PHASE teacher_begin 20\n", None, False, 2)

    def test_devices_separate_and_single_runtime_sample(self):
        state = {
            "path": "x.scope",
            "memory_current": 123,
            "memory_peak": 199,
            "swap_current": 0,
            "memory_stat": {
                "anon": 90,
                "file": 20,
                "file_mapped": 15,
                "shmem": 0,
                "pgscan": 4,
                "pgsteal": 3,
            },
            "pressure": {k: {"total": 5, "avg10": 0.1} for k in ("some", "full")},
            "events": {"oom": 0},
        }
        row = {
            "elapsed_s": 0.1,
            "cgroup": state,
            "disk_read_sectors": 500,
            "io": {"259:0": {"rbytes": 3, "rios": 1}},
            "proc": {"VmRSS": 123},
            "smaps": {},
            "resource_observation": {"host_psi_full_avg10": 0.4},
        }
        end = state | {
            "memory_current": 40,
            "memory_stat": state["memory_stat"] | {"anon": 0, "pgscan": 7},
        }
        r = review.resources(
            [row],
            end,
            {
                "elapsed_s": 0.5,
                "samples": 1,
                "io_by_device": {"259:0": {"rbytes": 10}},
                "namespace_read_bytes": 512,
            },
        )
        self.assertEqual(
            r["gauge_bytes"]["anon"], {"first": 90, "last": 90, "max_sampled": 90, "post_child": 0}
        )
        self.assertEqual(r["memory_stat_counters"]["pgscan"]["first_sample_to_post_child"], 3)
        self.assertIsNone(r["namespace_rbytes_first_to_last_sample"])
        self.assertEqual(r["cgroup_io_before_spawn_to_post_child"]["259:0"]["rbytes"], 10)
        self.assertEqual(r["namespace_rbytes_before_spawn_to_post_child"], 512)
        self.assertEqual(r["kernel_memory_peak_bytes"], 199)

    def test_empty_pre_spawn_and_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            (base / "raw").mkdir()
            log = base / "raw" / "native.stdout"
            log.write_bytes(b"")
            r = {
                "arm": "D0",
                "status": "FAIL_PRESERVED",
                "model_starts": 0,
                "raw_sha256": {"native.stdout": review.auth.sha(log)},
                "logits_sha256": {},
            }
            file = base / "receipt.json"
            file.write_text(json.dumps(r))
            digest = review.auth.sha(file)
            audited = review.audit(base, digest)
            self.assertEqual(audited["arm_status"], "FAIL_PRESERVED")
            self.assertIsNone(audited["resources"]["kernel_memory_peak_bytes"])
            log.write_bytes(b"x")
            with self.assertRaises(ValueError):
                review.audit(base, digest)


if __name__ == "__main__":
    unittest.main()
