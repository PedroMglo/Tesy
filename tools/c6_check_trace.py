#!/usr/bin/env python3
"""Validate the diagnostic target CPU Flash branch witness separately from timing."""

import hashlib
import json
from pathlib import Path

from c2_gate import strict_json
from c3_compare_capture_logits import resources
from c5_compare import ROOT, IDS, IDS_SHA, MODEL, MODEL_SHA, VOCAB, write_new

NAME = "c6-d2diag-dispatch-c64-on01"
OUT = ROOT / "results/c6-d2-dispatch-witness01.json"
PATCH = "c4104706a123ea92fb47bfab9a1f95a4e6cf106d"
BIN = "846201add96d67dd03e09bc3eb8f75080d0cb9966c3327a662bb9734c30774b2"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    if OUT.exists():
        raise SystemExit("no-replace dispatch witness exists")
    try:
        p = ROOT / "results" / NAME
        m = strict_json(Path(str(p)+".json").read_text())
        expected_env = {"LLAMA_MOE_STREAM_NO_PRELOAD": "1",
                        "TESY_CPU_FA_PREFILL_VEC_COMPAT": "1",
                        "TESY_CPU_FA_DISPATCH_TRACE": "1"}
        expected_cmd = ["tools/c6_prefill_probe_ub64", MODEL, IDS,
                        f"results/{NAME}", "short"]
        if m.get("run_id") != NAME or m.get("backend_sha") != PATCH or \
           m.get("binary_sha256") != BIN or m.get("explicit_env") != expected_env or \
           m.get("command") != expected_cmd or m.get("workload_sha256") != IDS_SHA or \
           m.get("artifact_identity", {}).get("sha256_previously_verified") != MODEL_SHA:
            raise ValueError("trace run identity/environment changed")
        resources(m, Path(str(p)+".samples.jsonl"))
        output = Path(str(p)+".f32").read_bytes()
        control = (ROOT/"results/c6-d2-c1-patched64-on-short01.f32").read_bytes()
        if len(output) != VOCAB*4 or output != control:
            raise ValueError("trace observer changed complete logits")
        lines = [line for line in Path(str(p)+".stderr").read_text().splitlines()
                 if line.startswith("TESY_CPU_FA_DISPATCH ")]
        common = "op=FLASH_ATTN_EXT device=CPU "
        first = f"TESY_CPU_FA_DISPATCH {common}nq=64 nkv=256 q=f32 k=f16 v=f16 mode=ON selected=1 branch=vector"
        tail = f"TESY_CPU_FA_DISPATCH {common}nq=49 nkv=256 q=f32 k=f16 v=f16 mode=ON selected=0 branch=vector"
        if len(lines) != 58 or lines.count(first) != 29 or lines.count(tail) != 29:
            raise ValueError("target CPU Flash branch witness changed")
        report = {"schema": "c6-d2-dispatch-witness-v1", "status": "PASS_DIAGNOSTIC_ONLY",
                  "run_manifest_sha256": sha(Path(str(p)+".json").read_bytes()),
                  "trace_stderr_sha256": sha(Path(str(p)+".stderr").read_bytes()),
                  "logits_sha256": sha(output), "logits_equal_untraced_C1": True,
                  "cpu_layer_invocations": {"nq64_compat_vector": 29, "nq49_original_vector": 29},
                  "timing_use": "DISALLOWED_OBSERVER_ACTIVE"}
    except Exception as exc:
        report = {"schema": "c6-d2-dispatch-witness-v1", "status": "FAIL_EVIDENCE",
                  "reason": f"{type(exc).__name__}: {exc}"}
    write_new(OUT, report)
    print(json.dumps({"status": report["status"], "reason": report.get("reason")}))
    return 0 if report["status"] == "PASS_DIAGNOSTIC_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
