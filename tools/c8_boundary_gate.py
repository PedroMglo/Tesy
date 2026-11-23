#!/usr/bin/env python3
"""Validate P8 native next-wave preload against the frozen no-preload profile."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

from c2_gate import GateError, strict_json
from c3_compare_capture_logits import resources
from c7_boundary_gate import capture, off, sha, LOGIT_PHASES, VOCAB

MODEL = "/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf"
BACKEND = "1248fd8fa8cfebaece5ea992e4d951c1e18bb9d5"


def preload_issued(log, expected_on):
    values = re.findall(r"preloads issued = (\d+)", log)
    if len(values) != 1 or (int(values[0]) > 0) != expected_on:
        raise GateError("next-wave preload activation differs from protocol")
    return int(values[0])


def source(stem, variant, binary, explicit_env, protocol):
    path = Path(str(stem) + ".json")
    manifest = strict_json(path.read_text())
    samples = resources(manifest, Path(str(stem) + ".samples.jsonl"))
    if manifest["run_id"] != stem.name or manifest["variant"] != variant or \
       manifest["command"][0] != binary or manifest["binary_sha256"] != sha(Path(binary)) or \
       manifest["model_path"] != MODEL or manifest["backend_sha"] != BACKEND or \
       manifest["workload_sha256"] != protocol["numeric_ids_sha256"] or \
       manifest["explicit_env"] != explicit_env or \
       manifest["relevant_environment"].get("LLAMA_MOE_STREAM_NO_PRELOAD") != explicit_env.get("LLAMA_MOE_STREAM_NO_PRELOAD") or \
       manifest["artifact_identity"]["stat_at_launch"] != protocol["model_stat"] or \
       manifest["artifact_identity"]["stat_at_end"] != protocol["model_stat"] or \
       manifest["mapped_backend_libraries_sha256"] != protocol["mapped_backend_libraries_sha256"] or \
       not manifest["mapped_libraries_match_ldd"]:
        raise GateError("P8 preload run identity differs from freeze: " + stem.name)
    for suffix,digest in manifest["output_sha256"].items():
        if sha(Path(str(stem) + suffix)) != digest:
            raise GateError("raw hash differs: " + stem.name + suffix)
    log = Path(str(stem) + ".stderr").read_text()
    placement = {int(i):dev for i,dev in re.findall(
        r"load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)",log)}
    if set(placement) != set(range(37)) or any(
        placement[i] != ("CPU" if i < 29 else "CUDA0") for i in range(37)) or \
       "MoE expert streaming uses O_DIRECT" not in log:
        raise GateError("P8 loader placement/O_DIRECT changed")
    preloads = preload_issued(log, not explicit_env)
    return manifest, {"manifest_sha256":sha(path),"sample_count":samples,
                      "preloads_issued":preloads}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("root",type=Path)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        protocol=strict_json((args.root/"protocol.json").read_text())
        ids=Path("results/c2-target-numeric-v1.ids")
        if sha(ids)!=protocol["numeric_ids_sha256"]:
            raise GateError("numeric input changed")
        row=next(x.split("\t") for x in ids.read_text().splitlines() if x.startswith("log_medium\t"))
        prompt,continuation=row[1].split(","),row[2].split(",")
        if len(prompt)!=189 or len(continuation)!=43:
            raise GateError("numeric ID schedule changed")
        specs=(("off1","P8-preload-off", "tools/c7_profile_probe",{"LLAMA_MOE_STREAM_NO_PRELOAD":"1"}),
               ("on","P8-preload-on-capture", "tools/c8_boundary_capture",{}),
               ("off2","P8-preload-off-repeat", "tools/c7_profile_probe",{"LLAMA_MOE_STREAM_NO_PRELOAD":"1"}))
        manifests=[];seals=[];off_logits=[]
        for label,variant,binary,env in specs:
            stem=args.root/"raw"/("c8-g2-"+label)
            manifest,seal=source(stem,variant,binary,env,protocol)
            manifests.append(manifest);seals.append(seal)
            if label!="on":
                logits,_=off(stem,(prompt,continuation))
                off_logits.append(logits)
        for key in ("model_id","model_path","backend_sha","backend_libraries_sha256",
                    "mapped_backend_libraries_sha256","workload_sha256"):
            if any(m[key]!=manifests[0][key] for m in manifests[1:]):
                raise GateError("cross-arm identity mismatch: "+key)
        on_logits,coverage=capture(args.root/"raw/c8-g2-on.capture")
        with (args.root/"raw/c8-g2-on.capture/byte_checks.tsv").open() as f:
            checked=list(csv.DictReader(f,delimiter="\t"))
        if not checked or any(row["status"]!="EQUAL" for row in checked):
            raise GateError("streamed expert byte/lifetime witness failed")
        mismatch=[]
        full_off1=(args.root/"raw/c8-g2-off1.f32").read_bytes()
        full_off2=(args.root/"raw/c8-g2-off2.f32").read_bytes()
        if full_off1!=full_off2:
            first=next(i for i in range(33*VOCAB) if
                       full_off1[4*i:4*i+4]!=full_off2[4*i:4*i+4])
            mismatch.append({"arm":"off2","phase":"all33","first_row":first//VOCAB,
                             "first_logit_index":first%VOCAB})
        for phase in LOGIT_PHASES:
            baseline=off_logits[0][phase]
            for arm,value in (("on",on_logits[phase]),("off2",off_logits[1][phase])):
                if baseline!=value:
                    first=next(i for i in range(VOCAB) if baseline[4*i:4*i+4]!=value[4*i:4*i+4])
                    mismatch.append({"arm":arm,"phase":phase,"first_logit_index":first})
        result={"schema":"c8-p8-preload-boundary-gate-v1",
                "status":"SAME_PROFILE_PASS" if not mismatch else "FAIL_SAME_PROFILE_FIDELITY",
                "mismatch":mismatch,"coverage":coverage,
                "all_33_off_repeat_bitwise":full_off1==full_off2,
                "all_byte_witness_rows_equal":True,
                "logit_sha256":{phase:hashlib.sha256(off_logits[0][phase]).hexdigest() for phase in LOGIT_PHASES},
                "arms":{label:seal for (label,*_),seal in zip(specs,seals)},
                "claim_limit":"full logits on five selected checkpoints and routed-layer capture; not independent attention/KV reference"}
    except (OSError,ValueError,KeyError,TypeError,IndexError,GateError) as exc:
        result={"schema":"c8-p8-preload-boundary-gate-v1","status":"FAIL_RESOURCES_OR_EVIDENCE",
                "reason":f"{type(exc).__name__}: {exc}"}
    with args.output.open("x") as f:
        json.dump(result,f,indent=2,sort_keys=True,allow_nan=False);f.write("\n")
    print(json.dumps({"status":result["status"],"reason":result.get("reason"),"mismatch":result.get("mismatch")}))
    return 0 if result["status"]=="SAME_PROFILE_PASS" else 1


if __name__=="__main__":
    raise SystemExit(main())
