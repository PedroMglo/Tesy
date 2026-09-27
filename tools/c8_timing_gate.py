#!/usr/bin/env python3
"""Fail-closed paired P8 native preload timing and bitwise analysis."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import struct

from c2_gate import GateError, strict_json
from c3_compare_capture_logits import resources
from c7_timing_gate import (ROW_BYTES,VOCAB,gain,ids_for,positive,sha,stream_stats,table)

MODEL = "/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf"
BINARY = "tools/c7_profile_probe"
ORDERS = {"screen113":(("off","on"),("on","off")),
          "screen496":(("off","on"),("on","off")),
          "confirm496":(("off","on"),("on","off"),("off","on"))}
CASES = {"screen113":("latency-short",113,"g3"),
         "screen496":("latency-medium",496,"g4"),
         "confirm496":("latency-medium",496,"g5")}


def classify(mode,pairs,med):
    if mode=="screen113":
        return "SHORT_FAVORABLE" if med["work_s"]>0 and med["prefill_s"]>0 and \
               med["tpot_aggregate_s"]>=-5 else "SHORT_NEUTRAL_OR_REGRESSION"
    if mode=="screen496":
        go=med["prefill_s"]>=10 and all(x["gains_pct"]["prefill_s"]>0 for x in pairs) and \
           med["work_s"]>=8 and med["tpot_aggregate_s"]>=-5
        return "SCREEN496_GO" if go else "NO_GO_PRELOAD_SCREEN496"
    if mode=="confirm496":
        go=med["prefill_s"]>=12 and med["work_s"]>=10 and \
           all(x["gains_pct"]["work_s"]>0 for x in pairs) and \
           med["tpot_aggregate_s"]>=-5
        return "CONFIRM496_GO" if go else "NO_GO_PRELOAD_CONFIRM496"
    raise GateError("unknown C8 timing classification")


def inspect(root,run_id,arm,case,count,commit,prompt,continuation,protocol):
    stem=root/"raw"/run_id
    path=Path(str(stem)+".json")
    m=strict_json(path.read_text())
    samples=resources(m,Path(str(stem)+".samples.jsonl"))
    env={"LLAMA_MOE_STREAM_NO_PRELOAD":"1"} if arm=="off" else {}
    cmd=[BINARY,MODEL,"results/c2-target-numeric-v1.ids","results/c3-p1-latency-ids01.tsv",
         str(stem),"--ngl","8","--case",case]
    if m["run_id"]!=run_id or m["variant"]!="P8-preload-"+arm+"-timing-"+case or \
       m["command"]!=cmd or m["binary_sha256"]!=protocol["binary_sha256"] or \
       m["backend_sha"]!=protocol["backend_commit"] or m["model_path"]!=MODEL or \
       m["workload_sha256"]!=protocol["timing_ids_sha256"] or \
       m["artifact_identity"]["stat_at_launch"]!=protocol["model_stat"] or \
       m["artifact_identity"]["stat_at_end"]!=protocol["model_stat"] or \
       m["explicit_env"]!=env or m["relevant_environment"]!=env or \
       m["mapped_backend_libraries_sha256"]!=protocol["mapped_backend_libraries_sha256"] or \
       not m["mapped_libraries_match_ldd"] or m["returncode"]!=0 or \
       m["stop_reason"] is not None:
        raise GateError("C8 timing arm identity/exit differs from freeze: "+run_id)
    for suffix,digest in m["output_sha256"].items():
        if sha(Path(str(stem)+suffix))!=digest:
            raise GateError("monitored raw hash differs: "+run_id+suffix)
    stderr=Path(str(stem)+".stderr").read_text()
    placed={int(i):d for i,d in re.findall(
        r"load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)",stderr)}
    if set(placed)!=set(range(37)) or any(placed[i]!=("CPU" if i<29 else "CUDA0")
                                           for i in range(37)) or \
       "MoE expert streaming uses O_DIRECT" not in stderr:
        raise GateError("P8 loader placement/O_DIRECT changed")
    expected=[{"phase":"prefill","position":str(count-1),"row":"0","token_id":prompt[-1]}]
    expected.extend({"phase":"decode","position":str(count+i),"row":str(i+1),
                     "token_id":continuation[i]} for i in range(32))
    if table(str(stem)+".rows.tsv",["phase","position","row","token_id"])!=expected:
        raise GateError("C8 output mask/position/ID changed")
    data=Path(str(stem)+".f32").read_bytes()
    if len(data)!=33*ROW_BYTES or any(not math.isfinite(x) for (x,) in struct.iter_unpack("<f",data)):
        raise GateError("C8 full logits incomplete/nonfinite")
    ops=table(str(stem)+".ops.tsv",["ngl","case","init_only","no_teacher","model_load_s",
                                  "context_init_s","prefill_completion_s","work_s","output_rows"])
    if len(ops)!=1 or [ops[0][k] for k in ("ngl","case","init_only","no_teacher","output_rows")]!=\
       ["8",case,"0","0","33"]:
        raise GateError("C8 effective operation plan changed")
    load=positive(ops[0]["model_load_s"],"model load")
    init=positive(ops[0]["context_init_s"],"context init")
    prefill=positive(ops[0]["prefill_completion_s"],"prefill completion")
    reported=positive(ops[0]["work_s"],"reported work")
    steps=table(str(stem)+".steps.tsv",["step","token_id","completion_s"])
    if len(steps)!=32 or any(x["step"]!=str(i) or x["token_id"]!=continuation[i]
                             for i,x in enumerate(steps)):
        raise GateError("C8 teacher-forced steps incomplete")
    step_s=[positive(x["completion_s"],"step completion") for x in steps]
    tpot=sum(step_s);work=prefill+tpot
    if abs(work-reported)>0.001:
        raise GateError("C8 reported work differs from phase sum")
    chunks=table(str(stem)+".chunks.tsv",["chunk","start","count","dispatch_s"])
    if len(chunks)!=(count+255)//256 or any(
        x["chunk"]!=str(i) or x["start"]!=str(i*256) or
        x["count"]!=str(min(256,count-i*256)) or positive(x["dispatch_s"],"chunk dispatch")<=0
        for i,x in enumerate(chunks)):
        raise GateError("C8 external prefill call plan changed")
    stats=stream_stats(stderr)
    if (stats["preloads_issued"]>0)!=(arm=="on"):
        raise GateError("C8 preload activation differs from frozen arm")
    return {"run_id":run_id,"arm":arm,"pair":int(re.search(r"pair(\d+)",run_id).group(1)),
            "measurement_commit":commit,"raw_manifest_sha256":sha(path),
            "logits_sha256":hashlib.sha256(data).hexdigest(),"sample_count":samples,
            "elapsed_s":m["elapsed_s"],"maxima":m["maxima"],
            "model_load_s":load,"context_init_s":init,"prefill_s":prefill,
            "tpot_aggregate_s":tpot,"tpot_mean_s":tpot/32,"step_s":step_s,
            "work_s":work,"cold_end_to_end_s":load+init+work,
            "stream_counters_source_names":stats,"proc_io_accounting":m["last_sample"]["proc"]},data


def main():
    p=argparse.ArgumentParser()
    p.add_argument("root",type=Path)
    p.add_argument("mode",choices=CASES)
    p.add_argument("measurement_commit")
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        protocol_path=args.root/("confirmation-protocol.json" if args.mode=="confirm496" else "timing-protocol.json")
        protocol=strict_json(protocol_path.read_text())
        case,count,gate=CASES[args.mode]
        prompt,continuation=ids_for(case)
        if sha("results/c3-p1-latency-ids01.tsv")!=protocol["timing_ids_sha256"] or \
           sha("results/c2-target-numeric-v1.ids")!=protocol["numeric_ids_sha256"] or \
           sha(BINARY)!=protocol["binary_sha256"] or \
           sha(args.root/"reference-complete.json")!=protocol["reference_complete_sha256"]:
            raise GateError("C8 timing inputs/binary/reference changed")
        arms=[]
        for pair,order in enumerate(ORDERS[args.mode],1):
            for arm in order:
                run_id=f"c8-{gate}-pair{pair}-{arm}"
                arms.append(inspect(args.root,run_id,arm,case,count,args.measurement_commit,
                                    prompt,continuation,protocol))
        control_key="screen496" if args.mode=="confirm496" else args.mode
        reference=Path(protocol["p8_control_raw"][control_key])
        if sha(reference)!=protocol["p8_control_sha256"][control_key]:
            raise GateError("contemporary P8 OFF control raw changed")
        baseline=reference.read_bytes()
        for seal,data in arms:
            if data!=baseline:
                first=next(i for i in range(33*VOCAB) if
                           data[4*i:4*i+4]!=baseline[4*i:4*i+4])
                raise GateError(f"FAIL_SAME_PROFILE_FIDELITY arm={seal['run_id']} row={first//VOCAB} logit={first%VOCAB}")
        pairs=[]
        for pair,order in enumerate(ORDERS[args.mode],1):
            off=next(seal for seal,_ in arms if seal["pair"]==pair and seal["arm"]=="off")
            on=next(seal for seal,_ in arms if seal["pair"]==pair and seal["arm"]=="on")
            pairs.append({"pair":pair,"order":list(order),
                          "off_run_id":off["run_id"],"on_run_id":on["run_id"],
                          "gains_pct":{key:gain(off[key],on[key]) for key in
                                       ("prefill_s","tpot_aggregate_s","work_s")},
                          "times_s":{"OFF":{k:off[k] for k in ("model_load_s","context_init_s",
                                           "prefill_s","tpot_aggregate_s","tpot_mean_s","work_s","cold_end_to_end_s")},
                                     "ON":{k:on[k] for k in ("model_load_s","context_init_s",
                                           "prefill_s","tpot_aggregate_s","tpot_mean_s","work_s","cold_end_to_end_s")}}})
        med={key:statistics.median(x["gains_pct"][key] for x in pairs) for key in
             ("prefill_s","tpot_aggregate_s","work_s")}
        status=classify(args.mode,pairs,med)
        result={"schema":"c8-p8-preload-paired-timing-v1","mode":args.mode,"case":case,
                "status":status,"measurement_commit":args.measurement_commit,
                "gain_formula":"100*(OFF-ON)/OFF","median_of_paired_gains_pct":med,
                "all_33_rows_same_profile_bitwise_to_contemporary_control":True,
                "pairs":pairs,"arms":[seal for seal,_ in arms],
                "claim_limit":"teacher-forced probe, n=2 screen or n=3 confirmation pairs; no API TTFT/quality/sampling or tail-latency claim"}
    except (OSError,ValueError,KeyError,TypeError,IndexError,GateError) as exc:
        reason=f"{type(exc).__name__}: {exc}"
        result={"schema":"c8-p8-preload-paired-timing-v1","mode":args.mode,
                "status":"FAIL_SAME_PROFILE_FIDELITY" if "FAIL_SAME_PROFILE_FIDELITY" in reason else "FAIL_RESOURCES_OR_EVIDENCE",
                "measurement_commit":args.measurement_commit,"reason":reason}
    with args.output.open("x") as f:
        json.dump(result,f,indent=2,sort_keys=True,allow_nan=False);f.write("\n")
    print(json.dumps({"status":result["status"],"median_gains":result.get("median_of_paired_gains_pct"),
                      "reason":result.get("reason")}))
    return 1 if result["status"].startswith("FAIL") else 0


if __name__=="__main__":
    raise SystemExit(main())
