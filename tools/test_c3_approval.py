#!/usr/bin/env python3
"""Model-free tests of the complete C3 approval chain."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import c2_publish_run
import c3_approve_run
from c2_gate import validate
from c2_server_run import normalize
from run_bounded import sha256
from test_c2_gate import fixture, frozen, H


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sample(t):
    events = {"max":0, "oom":0, "oom_kill":0}
    cgroup = {"path":"/c3-test.scope", "memory_max":1000, "swap_max":0,
              "memory_current":100, "memory_peak":150, "swap_current":0,
              "events":copy.deepcopy(events), "events_local":copy.deepcopy(events)}
    return {"elapsed_s":t, "pid":1234,
            "process_identity":{"pid":1234,"start_ticks":45678,
                                "cgroup_path":"/c3-test.scope","cgroup_inode":987},
            "proc":{"VmRSS":80,"VmSwap":0}, "cgroup":cgroup,
            "gpu":{"used_mib":25,"temperature_c":45},
            "thermal":{"cpu_tctl_c":50,"nvme_composite_c":40},
            "mem_available_bytes":900,"model_fds":{},"collection_s":0.01}


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "results").mkdir()
        (self.root / "workloads").mkdir()
        self.stem = self.root / "results" / "c3-approval-test"
        self.protocol_path = self.root / "workloads" / "protocol.json"
        self.doc = fixture()
        self.doc["run_id"] = self.stem.name
        self.protocol = frozen(self.doc)
        write(self.protocol_path, self.protocol)
        self.samples = [sample(t) for t in range(11)]
        self.launch_identity = copy.deepcopy(self.samples[0]["process_identity"])
        self.preflight = {"schema_version":"c2-server-preflight-v1",
                          "run_id":self.stem.name,"protocol_sha256":sha256(self.protocol_path),
                          "protocol":self.protocol,
                          "config":{"run_id":self.stem.name,"suite":"smoke1",
                                    "request_policy":{"max_tokens":64}},
                          "runner_sha256":H,"cgroup_start":copy.deepcopy(self.samples[0]["cgroup"])}
        self.raw_rows = [
            {"id":"one","started_s":1,"ended_s":4,"finish_reason":"stop",
             "usage":{"prompt_tokens":10,"completion_tokens":4,"total_tokens":14,
                      "prompt_tokens_details":{"cached_tokens":0}},
             "timings":{"cache_n":0,"prompt_ms":1000,"predicted_ms":1000}},
            {"id":"two","started_s":5,"ended_s":9,"finish_reason":"length",
             "usage":{"prompt_tokens":12,"completion_tokens":6,"total_tokens":18,
                      "prompt_tokens_details":{"cached_tokens":0}},
             "timings":{"cache_n":0,"prompt_ms":1000,"predicted_ms":2000}},
        ]
        self.stderr = ("slot print_timing: id 0 | task 17 | prompt eval time = 1000.00 ms / 10 tokens\n"
                       "slot print_timing: id 0 | task 17 | eval time = 1000.00 ms / 4 tokens\n"
                       "slot print_timing: id 0 | task 19 | prompt eval time = 1000.00 ms / 12 tokens\n"
                       "slot print_timing: id 0 | task 19 | eval time = 2000.00 ms / 6 tokens\n")
        self.end = copy.deepcopy(self.samples[-1]["cgroup"])

    def seal(self):
        stem = self.stem
        write(Path(str(stem)+".preflight.json"), self.preflight)
        identity = self.launch_identity
        launch = {"schema_version":"c3-launch-v1","run_id":stem.name,
                  "process_identity":copy.deepcopy(identity),
                  "cgroup_start":copy.deepcopy(self.preflight["cgroup_start"]),
                  "preflight_sha256":sha256(Path(str(stem)+".preflight.json"))}
        write(Path(str(stem)+".launch.json"), launch)
        Path(str(stem)+".stdout").write_text("")
        Path(str(stem)+".stderr").write_text(self.stderr)
        Path(str(stem)+".samples.jsonl").write_text(
            "".join(json.dumps(row, allow_nan=False)+"\n" for row in self.samples))
        extended = dict(self.preflight, launch_identity=copy.deepcopy(identity),
                        actually_loaded_backend_libraries_sha256=self.protocol["identity"]["library_sha256"])
        raw = {"schema_version":"c2-server-raw-v1","preflight":extended,
               "elapsed_s":10,"returncode":0,"stop_reasons":[],
               "results":self.raw_rows,"cgroup_end":self.end,
               "sample_count":len(self.samples),"launch_identity":copy.deepcopy(identity),
               "source_sha256":{suffix:sha256(Path(str(stem)+suffix)) for suffix in
                                (".launch.json",".stdout",".stderr",".samples.jsonl")}}
        write(Path(str(stem)+".json"), raw)
        normalized = normalize(self.raw_rows,self.protocol,extended["config"],self.samples,
                               self.stderr,10,0,[])
        write(Path(str(stem)+".normalized.json"), normalized)
        gate = validate(normalized,self.protocol)
        gate.update(source_sha256=sha256(Path(str(stem)+".normalized.json")),
                    protocol_sha256=sha256(self.protocol_path))
        write(Path(str(stem)+".gate.json"), gate)
        with mock.patch.object(c2_publish_run,"ROOT",self.root), \
             mock.patch.object(c2_publish_run.subprocess,"check_output",return_value="a"*40):
            c2_publish_run.publish(stem.name,self.protocol_path)
        return raw,gate

    def approve(self):
        with mock.patch.object(c3_approve_run,"ROOT",self.root):
            return c3_approve_run.approval(self.stem,self.protocol_path)

    def test_valid(self):
        self.seal()
        self.assertEqual(self.approve()["status"],"PASS")

    def test_nonzero_oom_before_first_sample(self):
        for group in ("events","events_local"):
            self.preflight["cgroup_start"][group]["oom"] = 1
            self.end[group]["oom"] = 1
            for row in self.samples:
                row["cgroup"][group]["oom"] = 1
        self.seal()
        self.assertEqual(validate(json.loads(Path(str(self.stem)+".normalized.json").read_text()),
                                  self.protocol)["status"],"PASS")
        with self.assertRaisesRegex(Exception,"pre-model OOM"):
            self.approve()

    def test_constant_pid_is_not_launch_pid(self):
        for row in self.samples:
            row["pid"] = 9999
            row["process_identity"]["pid"] = 9999
        self.seal()
        self.assertEqual(validate(json.loads(Path(str(self.stem)+".normalized.json").read_text()),
                                  self.protocol)["status"],"PASS")
        with self.assertRaisesRegex(Exception,"sample process/cgroup"):
            self.approve()

    def test_event_after_last_sample_and_publication_fail(self):
        self.end["events_local"]["oom"] = 1
        self.seal()
        published = json.loads(Path(str(self.stem)+".published.json").read_text())
        self.assertEqual(published["status"],"FAIL_END_RESOURCE")
        self.assertEqual(json.loads(Path(str(self.stem)+".gate.json").read_text())["status"],"PASS")
        with self.assertRaisesRegex(Exception,"event changed"):
            self.approve()

    def test_gate_pass_publication_fail(self):
        self.seal()
        path = Path(str(self.stem)+".published.json")
        report = json.loads(path.read_text())
        report["status"] = "FAIL_END_RESOURCE"
        report["end_resource_ok"] = False
        write(path,report)
        with self.assertRaisesRegex(Exception,"publication/end-resource"):
            self.approve()

    def test_missing_or_truncated_telemetry(self):
        self.seal()
        path = Path(str(self.stem)+".samples.jsonl")
        path.write_text(path.read_text()[:-3])
        with self.assertRaises(Exception):
            self.approve()


if __name__ == "__main__":
    unittest.main()
