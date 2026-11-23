#!/usr/bin/env python3
"""One-variable ub32/ub64 short numeric gate; timing is diagnostic on mismatch."""

import hashlib
import json
import math
from pathlib import Path
import struct

from c2_gate import strict_json
from c3_compare_capture_logits import resources
from c4_compare_numeric import top_two

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / "results/c4-q0-short-off01"
CANDIDATE = ROOT / "results/c4-p1-ub64-short01"
OUT = ROOT / "results/c4-p1-ub64-short-comparison01.json"
VOCAB = 201088


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if OUT.exists():
        raise SystemExit("no-replace output exists")
    try:
        source32 = (ROOT / "tools/c4_prefill_probe.cpp").read_text()
        source64 = (ROOT / "tools/c4_ub64_probe.cpp").read_text()
        if source64.replace("cp.n_ubatch=64", "cp.n_ubatch=32") != source32 or \
           source64.count("cp.n_ubatch=64") != 1:
            raise ValueError("probe source differs beyond ubatch")
        stems = (CONTROL, CANDIDATE)
        manifests = [strict_json(Path(str(stem)+".json").read_text()) for stem in stems]
        for stem, manifest in zip(stems, manifests):
            resources(manifest, Path(str(stem)+".samples.jsonl"))
        for key in ("model_id", "model_path", "artifact_identity", "backend_sha",
                    "backend_libraries_sha256", "workload_sha256"):
            if manifests[0][key] != manifests[1][key]:
                raise ValueError(f"provenance mismatch: {key}")
        if any(m["explicit_env"].get("LLAMA_MOE_STREAM_NO_PRELOAD") != "1" for m in manifests):
            raise ValueError("preload mode changed")
        commands = [m["command"] for m in manifests]
        if commands[0][1:3] != commands[1][1:3] or \
           any(command[-1] != "short" for command in commands):
            raise ValueError("model/IDs/mode command changed")
        rows = [Path(str(stem)+".rows.tsv").read_bytes() for stem in stems]
        if rows[0] != rows[1] or rows[0] != b"case\trow\ttokens\nlatency-short\t0\t113\n":
            raise ValueError("prompt output mask/rows changed")
        logits = [Path(str(stem)+".f32").read_bytes() for stem in stems]
        if any(len(payload) != VOCAB * 4 for payload in logits):
            raise ValueError("full logits vector incomplete")
        tops = [top_two(payload) for payload in logits]
        unequal = 0
        first = None
        max_abs = 0.0
        sum_sq = 0.0
        for i, (left, right) in enumerate(zip(struct.iter_unpack("<f", logits[0]),
                                               struct.iter_unpack("<f", logits[1]))):
            a, b = left[0], right[0]
            if not math.isfinite(a) or not math.isfinite(b):
                raise ValueError("nonfinite full logit")
            if logits[0][i*4:(i+1)*4] != logits[1][i*4:(i+1)*4]:
                unequal += 1
                if first is None:
                    first = i
            delta = a - b
            max_abs = max(max_abs, abs(delta))
            sum_sq += delta * delta
        case_times = []
        for stem in stems:
            lines = Path(str(stem)+".cases.tsv").read_text().splitlines()
            if len(lines) != 2 or not lines[1].startswith("latency-short\t113\t"):
                raise ValueError("timing case schedule differs")
            cols = lines[1].split("\t")
            timing = {"dispatch_s": float(cols[2]), "completion_s": float(cols[3]),
                      "pending_tail_s": float(cols[4])}
            if any(not math.isfinite(x) or x < 0 for x in timing.values()) or \
               timing["completion_s"] < timing["dispatch_s"]:
                raise ValueError("completed prefill timing invalid")
            case_times.append(timing)
        equal = unequal == 0
        result = {"schema": "c4-p1-ub64-short-v1",
                  "status": "SHORT_NUMERIC_BITWISE_PASS" if equal else
                            "NON_BITWISE_REQUIRES_SEPARATE_QUALIFICATION",
                  "scope": "same 113 IDs, external batch 256, final-token output mask, fresh process, no preload",
                  "different_float32_count": unequal, "first_different_logit": first,
                  "max_abs_logit_difference": max_abs,
                  "logit_rmse": math.sqrt(sum_sq / VOCAB),
                  "top_two": {"ub32": tops[0], "ub64": tops[1]},
                  "prefill_clocks_diagnostic_only": {"ub32": case_times[0], "ub64": case_times[1]},
                  "source_sha256": {str(path.relative_to(ROOT)): sha(path) for path in
                                    (ROOT / "tools/c4_prefill_probe.cpp",
                                     ROOT / "tools/c4_ub64_probe.cpp",
                                     *(Path(str(stem)+suffix) for stem in stems
                                       for suffix in (".json", ".rows.tsv", ".f32", ".cases.tsv")))},
                  "analyzer_sha256": sha(Path(__file__))}
    except (OSError, ValueError, KeyError, TypeError, struct.error) as exc:
        result = {"schema": "c4-p1-ub64-short-v1", "status": "FAIL_EVIDENCE",
                  "reason": f"{type(exc).__name__}: {exc}"}
    with OUT.open("x") as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"status": result["status"], "different_float32_count": result.get("different_float32_count"),
                      "first": result.get("first_different_logit"), "reason": result.get("reason")}))
    return 0 if result["status"] == "SHORT_NUMERIC_BITWISE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
