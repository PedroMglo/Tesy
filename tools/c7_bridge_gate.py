#!/usr/bin/env python3
"""C7 P8 short-prefill bridge against the unmodified C4 probe."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import struct

from c2_gate import GateError, strict_json
from c3_compare_capture_logits import resources

MODEL = "/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf"
C4_BINARY = "/home/pmglo/Projects/Tesy/tesy-scale-lab/tools/c4_prefill_probe"
C7_BINARY = "tools/c7_profile_probe"
VOCAB = 201088


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(stem, variant, binary, case):
    path = Path(str(stem)+".json")
    manifest = strict_json(path.read_text())
    samples = resources(manifest, Path(str(stem)+".samples.jsonl"))
    if manifest["run_id"] != stem.name or manifest["variant"] != variant or \
       manifest["binary_sha256"] != sha(Path(binary)) or \
       manifest["model_path"] != MODEL or \
       manifest["artifact_identity"]["stat_at_launch"] != manifest["artifact_identity"]["stat_at_end"] or \
       manifest["mapped_backend_libraries_sha256"] != manifest["backend_libraries_sha256"] or \
       not manifest["mapped_libraries_match_ldd"] or \
       manifest["explicit_env"] != {"LLAMA_MOE_STREAM_NO_PRELOAD": "1"}:
        raise GateError("P8 bridge provenance mismatch")
    for suffix, value in manifest["output_sha256"].items():
        if sha(Path(str(stem)+suffix)) != value:
            raise GateError("P8 bridge monitored raw hash changed")
    log = Path(str(stem)+".stderr").read_text()
    placement = {int(layer): device for layer, device in re.findall(
        r"load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)", log)}
    if set(placement) != set(range(37)) or \
       any(placement[i] != ("CPU" if i < 29 else "CUDA0") for i in range(37)) or \
       "MoE expert streaming uses O_DIRECT" not in log:
        raise GateError("P8 loader placement/O_DIRECT changed")
    rows_path = Path(str(stem)+".rows.tsv")
    with rows_path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows = list(reader)
    if case == "c4":
        if reader.fieldnames != ["case","row","tokens"] or rows != [
            {"case":"latency-short","row":"0","tokens":"113"}]:
            raise GateError("C4 prefill output mask/index changed")
    else:
        ids = Path("results/c3-p1-latency-ids01.tsv").read_text().splitlines()[0].split("\t")[1].split(",")
        if reader.fieldnames != ["phase","position","row","token_id"] or rows != [
            {"phase":"prefill","position":"112","row":"0","token_id":ids[-1]}]:
            raise GateError("C7 P8 prefill output mask/index changed")
    payload = Path(str(stem)+".f32").read_bytes()
    if len(payload) != VOCAB*4 or any(not math.isfinite(value) for (value,) in struct.iter_unpack("<f",payload)):
        raise GateError("P8 bridge logits incomplete/nonfinite")
    return manifest, payload, {"manifest_sha256":sha(path),
                               "logits_sha256":hashlib.sha256(payload).hexdigest(),
                               "rows_sha256":sha(rows_path), "samples":samples}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("c4",type=Path)
    p.add_argument("c7",type=Path)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--measurement-commit",required=True)
    args=p.parse_args()
    try:
        old, left, old_seal = inspect(args.c4,"P8-C4-original-bridge",C4_BINARY,"c4")
        new, right, new_seal = inspect(args.c7,"P8-C7-parametric-bridge",C7_BINARY,"c7")
        if old["backend_sha"] != new["backend_sha"] or \
           old["backend_libraries_sha256"] != new["backend_libraries_sha256"] or \
           old["workload_sha256"] != new["workload_sha256"] or \
           old["artifact_identity"]["stat_at_launch"] != new["artifact_identity"]["stat_at_launch"]:
            raise GateError("P8 bridge backend/model/workload identity differs")
        first = next((i for i in range(VOCAB) if left[4*i:4*i+4] != right[4*i:4*i+4]),None)
        status = "P8_BRIDGE_PASS" if first is None else "FAIL_NUMERIC_BRIDGE"
        result = {"schema":"c7c-p8-probe-bridge-v1","status":status,
                  "measurement_commit":args.measurement_commit,
                  "complete_logits_bitwise":first is None,
                  "first_mismatch_logit":first,
                  "sources":{"c4":old_seal,"c7":new_seal},
                  "claim_limit":"one 113-ID P8 prefill, no teacher forcing; not a timing comparison"}
    except (OSError,ValueError,KeyError,TypeError,GateError) as exc:
        result = {"schema":"c7c-p8-probe-bridge-v1","status":"FAIL_RESOURCES_OR_EVIDENCE",
                  "measurement_commit":args.measurement_commit,
                  "reason":f"{type(exc).__name__}: {exc}"}
    with args.output.open("x") as f:
        json.dump(result,f,indent=2,sort_keys=True,allow_nan=False);f.write("\n")
    print(json.dumps({"status":result["status"],"first_mismatch_logit":result.get("first_mismatch_logit"),
                      "reason":result.get("reason")}))
    return 0 if result["status"]=="P8_BRIDGE_PASS" else 1


if __name__=="__main__":
    raise SystemExit(main())
