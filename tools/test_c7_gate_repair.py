"""Mutations of the observed C6 capture and bounded-resource blind spots."""

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import c6_compare_d2 as c6
from c2_gate import GateError, strict_json
from c3_compare_capture_logits import resources
from run_bounded import mapped_libraries_match


class CaptureRepair(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.stem = "c6-d2diag-layer-aplus32-on01"
        self.raw = self.root / "results" / (self.stem + ".raw")
        self.raw.mkdir(parents=True)
        self.header = ["chunk", "stage", "layer", "first_abs", "n_tokens",
                       "type", "ne", "nb", "bytes", "file"]
        self.rows = []
        for chunk, start, n in ((0,0,32),(1,32,32),(2,64,32),(3,96,17)):
            for stage, layers in (("attn_norm", (0,)), ("l_out", range(36))):
                for layer in layers:
                    masked = stage == "l_out" and layer == 35 and chunk < 3
                    count = 0 if masked else 1 if stage == "l_out" and layer == 35 else n
                    first = -1 if masked else 112 if count == 1 else start
                    name = "-" if masked else f"chunk{chunk}_{stage}_{layer}.f32"
                    self.rows.append(dict(zip(self.header, (str(chunk), stage, str(layer), str(first),
                        str(count), "f32", f"2880,{count},1,1",
                        f"4,11520,{11520*count},{11520*count}", str(11520*count), name))))
                    if not masked:
                        with (self.raw/name).open("wb") as out:
                            out.truncate(11520*count)
        self.write_index()

    def write_index(self):
        with (self.raw/"index.tsv").open("w", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=self.header, delimiter="\t")
            writer.writeheader(); writer.writerows(self.rows)

    def check(self):
        with mock.patch.object(c6, "ROOT", self.root):
            return c6.capture_rows(self.stem)

    def test_valid_including_masked_zero_rows(self):
        rows, seal = self.check()
        self.assertEqual(len(rows), 36*113+1)
        self.assertEqual(seal["raw_file_count"], 145)

    def test_zero_payload_claiming_113_rows_and_one_feature_claiming_2880(self):
        row = self.rows[0]
        payload = self.raw/row["file"]
        for size in (0, 32*4):
            with self.subTest(size=size):
                with payload.open("wb") as out: out.truncate(size)
                with self.assertRaisesRegex(c6.EvidenceError, "truncated"):
                    self.check()

    def test_schema_chunk_position_stride_shape_and_dtype(self):
        row = self.rows[0]
        for field, bad in (("stage", "unfrozen"), ("chunk", "9"), ("first_abs", "1"),
                           ("n_tokens", "113"), ("ne", "1,32,1,1"),
                           ("nb", "4,4,128,128"), ("bytes", "128"), ("type", "f16")):
            with self.subTest(field=field):
                old = row[field]; row[field] = bad; self.write_index()
                with self.assertRaises(c6.EvidenceError): self.check()
                row[field] = old
        self.write_index()

    def test_missing_extra_duplicate_state_and_file(self):
        saved = self.rows.pop(); self.write_index()
        with self.assertRaisesRegex(c6.EvidenceError, "missing capture states"):
            self.check()
        self.rows.append(saved)
        self.rows.append(dict(saved)); self.write_index()
        with self.assertRaisesRegex(c6.EvidenceError, "duplicate"):
            self.check()
        self.rows.pop()
        self.rows[0]["stage"] = "extra"; self.write_index()
        with self.assertRaisesRegex(c6.EvidenceError, "extra"):
            self.check()
        self.rows[0]["stage"] = "attn_norm"; self.write_index()
        (self.raw/"unindexed.f32").write_bytes(b"\0\0\0\0")
        with self.assertRaisesRegex(c6.EvidenceError, "extra/missing capture files"):
            self.check()

    def test_only_frozen_mask_may_have_zero_rows(self):
        row = self.rows[0]
        old = dict(row)
        row.update(first_abs="-1", n_tokens="0", ne="2880,0,1,1",
                   nb="4,11520,0,0", bytes="0", file="-")
        self.write_index()
        with self.assertRaisesRegex(c6.EvidenceError, "invalid empty output"):
            self.check()
        row.update(old)

    def test_comparison_rejects_empty_rows(self):
        states = {("attn_norm",0,t):b"" for t in range(113)}
        with self.assertRaisesRegex(c6.EvidenceError, "shape changed"):
            c6.comparison(states, states, "attn_norm", 0, range(113))


class ClassificationRepair(unittest.TestCase):
    def test_c_equals_a_and_earlier_difference(self):
        equal = {"different_f32":0,"first_difference":None}
        diff = {"different_f32":1,"first_difference":{"absolute_token":7,"feature":3}}
        layers = {str(i):dict(equal) for i in range(36)}
        gpuop = {s:dict(equal) for s in ("attn_norm","attn_out","ffn_inp",
                    "attn_post_norm","ffn_moe_out","l_out")}
        gpuattn = {s:dict(equal) for s in ("Q_proj","Q_bias","Q_reshape","Q_rope",
                    "K_proj","K_bias","K_reshape","K_rope","V_proj","V_bias",
                    "V_reshape","flash_attn")}
        sources = {"q":{"common_input_equal":True}}
        replay = {"same_common_input_shape32_equals_A32":True,
                  "same_common_input_shape64_second32_differs":True}
        self.assertEqual(c6.classify_diagnostic(True,layers,gpuop,gpuattn,sources,replay)[0],
                         "COMPAT_RECOVERED")
        gpuattn["flash_attn"] = diff
        self.assertEqual(c6.classify_diagnostic(False,layers,gpuop,gpuattn,sources,replay)[1]
                         ["absolute_token"], 7)
        layers["24"] = diff
        status, location = c6.classify_diagnostic(False,layers,gpuop,gpuattn,sources,replay)
        self.assertEqual((status,location["stage"]), ("EARLIER_DIVERGENCE","24"))


class ResourceRepair(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/"samples.jsonl"
        self.identity = {"pid":123,"start_ticks":456,"cgroup_path":"/unit.scope",
                         "cgroup_inode":789}
        cg = {"path":"/unit.scope","memory_max":18*2**30,"swap_max":0,
              "memory_current":100,"memory_peak":150,"swap_current":0,
              "events":{"max":0,"oom":0,"oom_kill":0},
              "events_local":{"max":0,"oom":0,"oom_kill":0}}
        self.samples = [{"elapsed_s":t,"pid":123,"process_identity":dict(self.identity),
                         "proc":{"VmRSS":80,"VmSwap":0,"VmHWM":80},"cgroup":json.loads(json.dumps(cg)),
                         "gpu":{"used_mib":25,"temperature_c":45},
                         "thermal":{"cpu_tctl_c":50,"nvme_composite_c":40},
                         "mem_available_bytes":8*2**30} for t in (0.1,0.9)]
        self.manifest = {"returncode":0,"stop_reason":None,"elapsed_s":1.0,
                         "process_identity":dict(self.identity),"cgroup_start":json.loads(json.dumps(cg)),
                         "cgroup_end":json.loads(json.dumps(cg)),"output_sha256":{}}
        self.seal()

    def seal(self):
        self.path.write_text("".join(json.dumps(s)+"\n" for s in self.samples))
        self.manifest["output_sha256"][".samples.jsonl"] = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def check(self):
        return resources(self.manifest,self.path)

    def test_valid(self):
        self.assertEqual(self.check(),2)

    def test_invalid_samples(self):
        mutations = (("rss missing",lambda s:s[0]["proc"].pop("VmRSS")),
                     ("pid changed",lambda s:s[1].update(pid=321)),
                     ("oom",lambda s:s[1]["cgroup"]["events"].update(oom=1)),
                     ("cgroup",lambda s:s[1]["cgroup"].update(path="/other")),
                     ("negative",lambda s:s[0]["proc"].update(VmRSS=-1)),
                     ("late",lambda s:s[1].update(elapsed_s=1.1)))
        original = json.loads(json.dumps(self.samples))
        for label, mutate in mutations:
            with self.subTest(label=label):
                self.samples = json.loads(json.dumps(original))
                mutate(self.samples); self.seal()
                with self.assertRaises(GateError): self.check()

    def test_bad_cap_hash_and_json_overflow(self):
        self.manifest["cgroup_end"]["memory_max"] = 19*2**30
        with self.assertRaises(GateError): self.check()
        self.manifest["cgroup_end"]["memory_max"] = 18*2**30
        self.path.write_text(self.path.read_text().replace("\n", " \n", 1))
        with self.assertRaisesRegex(GateError,"hash"):
            self.check()
        with self.assertRaisesRegex(GateError,"nonfinite"):
            strict_json('{"x":1e309}')

    def test_unexpected_or_missing_mapping(self):
        expected = {"libggml.so":"a"*64}
        self.assertTrue(mapped_libraries_match(expected,dict(expected)))
        self.assertFalse(mapped_libraries_match(expected,{}))
        self.assertFalse(mapped_libraries_match(expected,{**expected,"/other/libggml.so":"b"*64}))


if __name__ == "__main__": unittest.main()
