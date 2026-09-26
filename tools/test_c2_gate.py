#!/usr/bin/env python3
"""Model-free mutation tests for every frozen C2-A fail-closed gate."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from c2_gate import GateError, strict_json, validate
from c2_compare_rows import compare


H = "a" * 64
SHA40 = "b" * 40


def fixture():
    return {
        "schema_version": "c2-run-v1", "campaign_id": "c2-test", "run_id": "run-1",
        "protocol_id": "test-protocol",
        "identity": {"model_id": "synthetic", "model_sha256": H, "backend_sha": SHA40,
                     "binary_sha256": H, "library_sha256": {"lib.so": H},
                     "config_sha256": H, "workload_sha256": H, "input_sha256": {"input.jsonl": H}},
        "expected_request_ids": ["one", "two"],
        "requests": [
            {"id": "one", "backend_task_id": 17, "started_s": 1, "ended_s": 4,
             "api_prompt_tokens": 10, "api_completion_tokens": 4,
             "backend_prompt_tokens": 10, "backend_completion_tokens": 4,
             "prefill_s": 1, "decode_s": 1, "finish_reason": "stop"},
            {"id": "two", "backend_task_id": 19, "started_s": 5, "ended_s": 9,
             "api_prompt_tokens": 12, "api_completion_tokens": 6,
             "backend_prompt_tokens": 12, "backend_completion_tokens": 6,
             "prefill_s": 1, "decode_s": 2, "finish_reason": "length"}],
        "samples": [
            {"t_s": t, "pid": 1234, "cgroup_memory_bytes": 100, "cgroup_peak_bytes": 150,
             "cgroup_swap_bytes": 0, "cgroup_max_events": 0, "cgroup_oom_events": 0,
             "cgroup_oom_kill_events": 0, "cgroup_local_max_events": 0,
             "cgroup_local_oom_events": 0, "cgroup_local_oom_kill_events": 0,
             "rss_bytes": 80, "proc_swap_bytes": 0, "gpu_used_mib": 25,
             "gpu_temperature_c": 45, "cpu_tctl_c": 50, "nvme_composite_c": 40,
             "mem_available_bytes": 900} for t in range(11)],
        "limits": {"memory_max_bytes": 1000, "rss_max_bytes": 500, "gpu_max_mib": 200,
                   "min_mem_available_bytes": 600, "cpu_max_c": 95, "gpu_max_c": 80,
                   "nvme_max_c": 70, "max_gap_s": 3, "boundary_s": 2,
                   "min_elapsed_s": 10, "min_active_s": 7, "min_decode_s": 3,
                   "min_decode_tok_s": 2, "min_last_half_tok_s": 2},
        "outcome": {"elapsed_s": 10, "returncode": 0, "stop_reasons": [],
                    "backend_errors": []},
    }


def frozen(doc=None):
    doc = doc or fixture()
    return {"schema_version": "c2-protocol-v1", "campaign_id": doc["campaign_id"],
            "protocol_id": doc["protocol_id"], "identity": copy.deepcopy(doc["identity"]),
            "expected_request_ids": copy.deepcopy(doc["expected_request_ids"]),
            "limits": copy.deepcopy(doc["limits"])}


class GateTests(unittest.TestCase):
    def assert_rejects(self, mutate):
        doc = fixture()
        mutate(doc)
        with self.assertRaises(GateError):
            validate(doc, frozen())

    def test_valid(self):
        self.assertEqual(validate(fixture(), frozen())["status"], "PASS")

    def test_api_backend_mismatch(self):
        self.assert_rejects(lambda d: d["requests"][0].__setitem__("api_completion_tokens", 5))

    def test_missing_request(self):
        self.assert_rejects(lambda d: d["requests"].pop())

    def test_duplicate_request(self):
        self.assert_rejects(lambda d: d["requests"][1].__setitem__("id", "one"))

    def test_duplicate_backend_task(self):
        self.assert_rejects(lambda d: d["requests"][1].__setitem__("backend_task_id", 17))

    def test_backend_task_order(self):
        self.assert_rejects(lambda d: d["requests"][1].__setitem__("backend_task_id", 16))

    def test_missing_timing(self):
        self.assert_rejects(lambda d: d["requests"][0].pop("decode_s"))

    def test_idle_time_does_not_count_as_active_service(self):
        self.assert_rejects(lambda d: d["limits"].__setitem__("min_active_s", 8))

    def test_workload_or_model_swapped(self):
        self.assert_rejects(lambda d: d["identity"].__setitem__("model_sha256", "c"*64))
        self.assert_rejects(lambda d: d["identity"].__setitem__("workload_sha256", "c"*64))

    def test_telemetry_empty(self):
        self.assert_rejects(lambda d: d.__setitem__("samples", []))

    def test_telemetry_gap(self):
        self.assert_rejects(lambda d: d.__setitem__("samples", d["samples"][:2] + d["samples"][6:]))

    def test_telemetry_nonmonotone(self):
        self.assert_rejects(lambda d: d["samples"][2].__setitem__("t_s", 1))

    def test_telemetry_wrong_run_pid(self):
        self.assert_rejects(lambda d: d["samples"][3].__setitem__("pid", 4567))

    def test_telemetry_missing_field(self):
        self.assert_rejects(lambda d: d["samples"][3].pop("cpu_tctl_c"))

    def test_peak_cannot_decrease(self):
        self.assert_rejects(lambda d: d["samples"][3].__setitem__("cgroup_peak_bytes", 99))

    def test_backend_error(self):
        self.assert_rejects(lambda d: d["outcome"]["backend_errors"].append("EIO"))

    def test_swap_oom_and_peak(self):
        self.assert_rejects(lambda d: d["samples"][3].__setitem__("proc_swap_bytes", 1))
        self.assert_rejects(lambda d: d["samples"][3].__setitem__("cgroup_oom_events", 1))
        self.assert_rejects(lambda d: d["samples"][3].__setitem__("cgroup_peak_bytes", 1001))

    def test_zero_negative_nonfinite_and_bool(self):
        for value in (0, -1, float("nan"), float("inf"), True):
            self.assert_rejects(lambda d: d["requests"][0].__setitem__("decode_s", value))

    def test_extra_duplicate_truncated_json(self):
        self.assert_rejects(lambda d: d.__setitem__("unexpected", 1))
        with self.assertRaises(GateError):
            strict_json('{"x":1,"x":2}')
        with self.assertRaises(GateError):
            strict_json('{"x":NaN}')
        with self.assertRaises(json.JSONDecodeError):
            strict_json('{"x":')

    def test_output_no_replace(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.json"
            protocol = Path(tmp) / "protocol.json"
            output = Path(tmp) / "result.json"
            source.write_text(json.dumps(fixture()))
            protocol.write_text(json.dumps(frozen()))
            cmd = [sys.executable, str(Path(__file__).with_name("c2_gate.py")),
                   str(source), "--protocol", str(protocol), "--output", str(output)]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)

    def test_numeric_gate_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            first, second, output = (Path(tmp)/name for name in ("a.f32", "b.f32", "report.json"))
            import struct
            first.write_bytes(struct.pack("<f", 1.0))
            second.write_bytes(struct.pack("<f", 2.0))
            cmd = [sys.executable, str(Path(__file__).with_name("compare_logits.py")),
                   str(first), str(second), "--output", str(output), "--require-bitwise"]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 1)
            self.assertFalse(json.loads(output.read_text())["bitwise_equal"])

    def test_multirow_numeric_gate_and_missing_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ids = root / "ids.tsv"
            ids.write_text("tiny\t1,2\t3\n")
            stems = [root / "reference", root / "candidate"]
            import struct
            for stem in stems:
                Path(str(stem)+".rows.tsv").write_text(
                    "case\tphase\tposition\trow\n"
                    "tiny\tprompt\t0\t0\n"
                    "tiny\tprompt\t1\t1\n"
                    "tiny\tcontinuation\t2\t2\n")
                Path(str(stem)+".f32").write_bytes(struct.pack("<9f", *range(9)))
                Path(str(stem)+".json").write_text(json.dumps({
                    "returncode":0,"stop_reason":None,"cgroup_limit_enforced":True,
                    "command":[str(stem),str(ids)],"model_id":"tiny","model_path":"tiny.gguf"}))
            args = [stems[0],stems[1],ids,"tiny",1,3,
                    Path(str(stems[0])+".json"),Path(str(stems[1])+".json")]
            self.assertTrue(compare(*args)["bitwise_equal"])
            Path(str(stems[1])+".f32").write_bytes(struct.pack("<9f",0,1,2,3,4,5,6,7,99))
            self.assertFalse(compare(*args)["bitwise_equal"])
            Path(str(stems[1])+".rows.tsv").write_text("case\tphase\tposition\trow\n")
            with self.assertRaises(GateError):
                compare(*args)

    def test_selected_case_with_global_row_offsets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ids = root / "ids.tsv"
            ids.write_text("first\t1,2\t3\nsecond\t4,5\t6\n")
            stems = [root / "reference", root / "candidate"]
            import struct
            for stem in stems:
                Path(str(stem)+".rows.tsv").write_text(
                    "case\tphase\tposition\trow\n"
                    "first\tprompt\t0\t0\nfirst\tprompt\t1\t1\n"
                    "first\tcontinuation\t2\t2\n"
                    "second\tprompt\t0\t3\nsecond\tprompt\t1\t4\n"
                    "second\tcontinuation\t2\t5\n")
                Path(str(stem)+".f32").write_bytes(struct.pack("<18f", *range(18)))
                Path(str(stem)+".json").write_text(json.dumps({
                    "returncode":0,"stop_reason":None,"cgroup_limit_enforced":True,
                    "command":[str(stem),str(ids)],"model_id":"tiny","model_path":"tiny.gguf"}))
            args = [stems[0],stems[1],ids,"second",1,3,
                    Path(str(stems[0])+".json"),Path(str(stems[1])+".json")]
            self.assertEqual(compare(*args)["n_rows"], 3)
            changed = list(range(18)); changed[17] = 99
            Path(str(stems[1])+".f32").write_bytes(struct.pack("<18f", *changed))
            mismatch = compare(*args)["mismatch_rows"]
            self.assertEqual([mismatch[0]["row"], mismatch[0]["global_row"]], [2, 5])


if __name__ == "__main__":
    unittest.main()
