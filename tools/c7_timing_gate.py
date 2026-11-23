#!/usr/bin/env python3
"""Fail-closed paired C7 P8/P12 teacher-forced timing analysis."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import struct

from c2_gate import GateError, strict_json
from c3_compare_capture_logits import resources

MODEL = "/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf"
BINARY = "tools/c7_profile_probe"
VOCAB = 201088
ROW_BYTES = VOCAB*4
SELECTED = (0,1,2,8,32)
CASES = {"screen113":("latency-short",113,"g3"),
         "screen496":("latency-medium",496,"g4"),
         "confirm496":("latency-medium",496,"g5"),
         "screen1522":("latency-long",1522,"g5long")}
ORDERS = {"screen113":(("P8","P12"),("P12","P8")),
          "screen496":(("P8","P12"),("P12","P8")),
          "confirm496":(("P8","P12"),("P12","P8"),("P8","P12")),
          "screen1522":(("P8","P12"),("P12","P8"))}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def table(path, header):
    with Path(path).open() as f:
        reader=csv.DictReader(f,delimiter="\t")
        if reader.fieldnames!=header:
            raise GateError("TSV schema changed: "+str(path))
        return list(reader)


def positive(value,name):
    try:
        x=float(value)
    except (TypeError,ValueError) as exc:
        raise GateError("invalid "+name) from exc
    if not math.isfinite(x) or x<=0:
        raise GateError("non-positive/nonfinite "+name)
    return x


def gain(control,candidate):
    if not math.isfinite(control) or not math.isfinite(candidate) or control<=0 or candidate<=0:
        raise GateError("invalid paired timing denominator/value")
    return 100.0*(control-candidate)/control


def ids_for(case):
    lines=[line.split("\t") for line in Path("results/c3-p1-latency-ids01.tsv").read_text().splitlines()]
    if [x[0] for x in lines]!=["latency-short","latency-medium","latency-long"]:
        raise GateError("timing case schedule changed")
    counts=(113,496,1522)
    if any(len(row)!=2 or len(row[1].split(","))!=count for row,count in zip(lines,counts)):
        raise GateError("timing ID count changed")
    numeric=[line.split("\t") for line in Path("results/c2-target-numeric-v1.ids").read_text().splitlines()]
    row=next((x for x in numeric if x[0]=="log_medium"),None)
    if row is None or len(row)!=3 or len(row[1].split(","))!=189 or len(row[2].split(","))!=43:
        raise GateError("teacher-forced IDs changed")
    return next(x[1].split(",") for x in lines if x[0]==case),row[2].split(",")[:32]


def stream_stats(log):
    block=re.findall(r"C7_STATS_BEGIN\n(.*?)C7_STATS_END",log,re.S)
    if len(block)!=1:
        raise GateError("stream stats missing/duplicated")
    source=block[0]
    first=re.search(r"remap calls = (\d+), expert hits = (\d+), misses = (\d+) \((\d+) cold\)",source)
    second=re.search(r"waves = (\d+) \((\d+) non-empty\), preloads issued = (\d+) \(ready on arrival = (\d+)\), wave stall = ([\d.]+) ms",source)
    if not first or not second:
        raise GateError("stream counters changed")
    stall=float(second.group(5))
    if not math.isfinite(stall) or stall<0:
        raise GateError("invalid diagnostic wave stall counter")
    return dict(zip(("remap_calls","expert_hits","misses","cold_misses",
                     "waves","non_empty_waves","preloads_issued","ready_on_arrival"),
                    [int(x) for x in first.groups()+second.groups()[:4]])) | {
                    "wave_stall_ms_diagnostic":stall}


def inspect(root,run_id,profile,case,count,commit,prompt,continuation,protocol):
    stem=root/"raw"/run_id
    path=Path(str(stem)+".json")
    m=strict_json(path.read_text())
    samples=resources(m,Path(str(stem)+".samples.jsonl"))
    cmd=[BINARY,MODEL,"results/c2-target-numeric-v1.ids","results/c3-p1-latency-ids01.tsv",
         str(stem),"--ngl","8" if profile=="P8" else "12","--case",case]
    if m["run_id"]!=run_id or m["variant"]!=profile+"-timing-"+case or m["command"]!=cmd or \
       m["binary_sha256"]!=protocol["binary_sha256"] or m["backend_sha"]!=protocol["backend_commit"] or \
       m["model_path"]!=MODEL or m["workload_sha256"]!=protocol["timing_ids_sha256"] or \
       m["artifact_identity"]["stat_at_launch"]!=protocol["model_stat"] or \
       m["artifact_identity"]["stat_at_end"]!=protocol["model_stat"] or \
       m["explicit_env"]!={"LLAMA_MOE_STREAM_NO_PRELOAD":"1"} or \
       m["mapped_backend_libraries_sha256"]!=m["backend_libraries_sha256"] or \
       not m["mapped_libraries_match_ldd"]:
        raise GateError("timing run identity differs from freeze: "+run_id)
    for suffix,digest in m["output_sha256"].items():
        if sha(Path(str(stem)+suffix))!=digest:
            raise GateError("monitored raw hash differs: "+run_id+suffix)
    stderr=Path(str(stem)+".stderr").read_text()
    placed={int(i):d for i,d in re.findall(
        r"load_tensors: layer\s+(\d+) assigned to device (CPU|CUDA0)",stderr)}
    first_gpu=29 if profile=="P8" else 25
    if set(placed)!=set(range(37)) or any(placed[i]!=("CPU" if i<first_gpu else "CUDA0") for i in range(37)) or \
       "MoE expert streaming uses O_DIRECT" not in stderr:
        raise GateError("timing loader map/O_DIRECT changed")
    expected=[{"phase":"prefill","position":str(count-1),"row":"0","token_id":prompt[-1]}]
    expected += [{"phase":"decode","position":str(count+i),"row":str(i+1),"token_id":continuation[i]}
                 for i in range(32)]
    if table(str(stem)+".rows.tsv",["phase","position","row","token_id"])!=expected:
        raise GateError("timing output mask/position/ID changed")
    data=Path(str(stem)+".f32").read_bytes()
    if len(data)!=33*ROW_BYTES or any(not math.isfinite(x) for (x,) in struct.iter_unpack("<f",data)):
        raise GateError("timing logits incomplete/nonfinite")
    ops=table(str(stem)+".ops.tsv",["ngl","case","init_only","no_teacher","model_load_s",
                                  "context_init_s","prefill_completion_s","work_s","output_rows"])
    if len(ops)!=1 or ops[0]["ngl"]!=("8" if profile=="P8" else "12") or \
       ops[0]["case"]!=case or ops[0]["init_only"]!="0" or ops[0]["no_teacher"]!="0" or \
       ops[0]["output_rows"]!="33":
        raise GateError("timing effective operations changed")
    load=positive(ops[0]["model_load_s"],"model load")
    init=positive(ops[0]["context_init_s"],"context init")
    prefill=positive(ops[0]["prefill_completion_s"],"prefill completion")
    work_reported=positive(ops[0]["work_s"],"reported work")
    steps=table(str(stem)+".steps.tsv",["step","token_id","completion_s"])
    if len(steps)!=32 or any(row["step"]!=str(i) or row["token_id"]!=continuation[i]
                             for i,row in enumerate(steps)):
        raise GateError("teacher-forced steps incomplete")
    step_s=[positive(row["completion_s"],"step completion") for row in steps]
    tpot=sum(step_s)
    work=prefill+tpot
    if abs(work-work_reported)>0.001:
        raise GateError("reported work differs from phase sum")
    chunks=table(str(stem)+".chunks.tsv",["chunk","start","count","dispatch_s"])
    expected_chunks=(count+255)//256
    if len(chunks)!=expected_chunks or any(
        row["chunk"]!=str(i) or row["start"]!=str(i*256) or
        row["count"]!=str(min(256,count-i*256)) or
        positive(row["dispatch_s"],"chunk dispatch")<=0 for i,row in enumerate(chunks)):
        raise GateError("external prefill call plan changed")
    stats=stream_stats(stderr)
    if stats["preloads_issued"]!=0:
        raise GateError("unexpected expert preload")
    seal={"run_id":run_id,"profile":profile,"pair":int(re.search(r"pair(\d+)",run_id).group(1)),
          "measurement_commit":commit,"manifest_sha256":sha(path),"logits_sha256":hashlib.sha256(data).hexdigest(),
          "samples":samples,"elapsed_s":m["elapsed_s"],"maxima":m["maxima"],
          "model_load_s":load,"context_init_s":init,"prefill_s":prefill,"step_s":step_s,
          "tpot_aggregate_s":tpot,"tpot_mean_s":tpot/32,"work_s":work,
          "cold_end_to_end_s":load+init+work,"stream_counters_source_names":stats,
          "proc_io_accounting":m["last_sample"]["proc"]}
    return seal,data


def top_two(raw):
    first=(-1,-math.inf);second=(-1,-math.inf)
    for i,(x,) in enumerate(struct.iter_unpack("<f",raw)):
        if x>first[1]:
            second,first=first,(i,x)
        elif x>second[1]:
            second=(i,x)
    return {"top1_id":first[0],"top1_logit":first[1],
            "top2_id":second[0],"top2_logit":second[1],"margin":first[1]-second[1]}


def cross_profile(left,right):
    result=[]
    for row in SELECTED:
        a=left[row*ROW_BYTES:(row+1)*ROW_BYTES]
        b=right[row*ROW_BYTES:(row+1)*ROW_BYTES]
        n=sum(a[i*4:i*4+4]!=b[i*4:i*4+4] for i in range(VOCAB))
        result.append({"row":row,"bitwise_mismatch_logits":n,
                       "p8_top_two":top_two(a),"p12_top_two":top_two(b)})
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("root",type=Path)
    p.add_argument("mode",choices=CASES)
    p.add_argument("measurement_commit")
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    try:
        protocol=strict_json((args.root/"timing-protocol.json").read_text())
        case,count,gate=CASES[args.mode]
        prompt,continuation=ids_for(case)
        if sha("results/c3-p1-latency-ids01.tsv")!=protocol["timing_ids_sha256"] or \
           sha("results/c2-target-numeric-v1.ids")!=protocol["numeric_ids_sha256"] or \
           sha(BINARY)!=protocol["binary_sha256"]:
            raise GateError("timing input/binary differs from freeze")
        arms=[]
        for pair,order in enumerate(ORDERS[args.mode],1):
            for profile in order:
                run_id=f"c7c-{gate}-pair{pair}-{profile.lower()}"
                arms.append(inspect(args.root,run_id,profile,case,count,args.measurement_commit,
                                    prompt,continuation,protocol))
        by_profile={"P8":[],"P12":[]}
        for seal,data in arms:
            by_profile[seal["profile"]].append((seal,data))
        for profile,group in by_profile.items():
            different=next((entry[1] for entry in group[1:] if group[0][1]!=entry[1]),None)
            if different is not None:
                first=next(i for i in range(33*VOCAB) if
                           group[0][1][4*i:4*i+4]!=different[4*i:4*i+4])
                raise GateError(f"FAIL_SAME_PROFILE_FIDELITY {profile} row={first//VOCAB} logit={first%VOCAB}")
        if args.mode=="screen113":
            c4=Path("results/c7c-20260927T1224Z/raw/c7c-p8-c4-bridge01.f32").read_bytes()
            if any(group[1][:ROW_BYTES]!=c4 for group in by_profile["P8"]):
                raise GateError("P8 screening prefill differs from C4 bridge")
        pairs=[];cross=[]
        for i in range(len(ORDERS[args.mode])):
            p8=next(seal for seal,data in arms if seal["pair"]==i+1 and seal["profile"]=="P8")
            p12=next(seal for seal,data in arms if seal["pair"]==i+1 and seal["profile"]=="P12")
            pairs.append({"pair":i+1,"order":list(ORDERS[args.mode][i]),
                          "p8_run_id":p8["run_id"],"p12_run_id":p12["run_id"],
                          "gains_pct":{key:gain(p8[key],p12[key]) for key in
                                       ("prefill_s","tpot_aggregate_s","work_s")},
                          "times_s":{"P8":{k:p8[k] for k in ("model_load_s","context_init_s","prefill_s",
                                                            "tpot_aggregate_s","tpot_mean_s","work_s","cold_end_to_end_s")},
                                     "P12":{k:p12[k] for k in ("model_load_s","context_init_s","prefill_s",
                                                              "tpot_aggregate_s","tpot_mean_s","work_s","cold_end_to_end_s")}}})
            left=next(data for seal,data in arms if seal["pair"]==i+1 and seal["profile"]=="P8")
            right=next(data for seal,data in arms if seal["pair"]==i+1 and seal["profile"]=="P12")
            cross.append({"pair":i+1,"selected_descriptive":cross_profile(left,right)})
        med={key:statistics.median(row["gains_pct"][key] for row in pairs) for key in
             ("prefill_s","tpot_aggregate_s","work_s")}
        if args.mode=="screen113":
            favorable=med["work_s"]>=3 and all(x["gains_pct"]["work_s"]>=-3 for x in pairs) and \
                      med["prefill_s"]>=-5 and med["tpot_aggregate_s"]>=-5
            status="SHORT_FAVORABLE" if favorable else (
                   "SHORT_REGRESSION" if med["work_s"]<0 or
                    any(x["gains_pct"]["work_s"]<-3 for x in pairs) or
                    min(med["prefill_s"],med["tpot_aggregate_s"])<-5 else "SHORT_NEUTRAL")
        elif args.mode=="screen496":
            go=med["work_s"]>=5 and all(x["gains_pct"]["work_s"]>0 for x in pairs) and \
               med["prefill_s"]>=-5 and med["tpot_aggregate_s"]>=-5
            status="SCREEN496_GO" if go else "NO_GO_SCREEN496"
        elif args.mode=="confirm496":
            go=med["work_s"]>=8 and all(x["gains_pct"]["work_s"]>0 for x in pairs) and \
               med["prefill_s"]>=-5 and med["tpot_aggregate_s"]>=-5
            status="CONFIRM496_GO" if go else "NO_GO_CONFIRM"
        else:
            go=med["work_s"]>=5 and all(x["gains_pct"]["work_s"]>=0 for x in pairs) and \
               med["prefill_s"]>=8 and med["tpot_aggregate_s"]>=-5
            status="LONG_SPECIALIZED_SCREEN_GO" if go else "NO_GO_LONG_SPECIALIZED_SCREEN"
        result={"schema":"c7c-paired-timing-v1","mode":args.mode,"case":case,"status":status,
                "measurement_commit":args.measurement_commit,"gain_formula":"100*(P8-P12)/P8",
                "median_of_paired_gains_pct":med,"pairs":pairs,
                "arms":[seal for seal,data in arms],"cross_profile_descriptive":cross,
                "claim_limit":"synthetic teacher-forced sequence; small paired sample; no API TTFT, sampling or quality claim"}
    except (OSError,ValueError,KeyError,TypeError,IndexError,GateError) as exc:
        reason=f"{type(exc).__name__}: {exc}"
        status="FAIL_SAME_PROFILE_FIDELITY" if "FAIL_SAME_PROFILE_FIDELITY" in reason else "FAIL_RESOURCES_OR_EVIDENCE"
        result={"schema":"c7c-paired-timing-v1","mode":args.mode,"status":status,
                "measurement_commit":args.measurement_commit,"reason":reason}
    with args.output.open("x") as f:
        json.dump(result,f,indent=2,sort_keys=True,allow_nan=False);f.write("\n")
    print(json.dumps({"status":result["status"],"median_gains":result.get("median_of_paired_gains_pct"),
                      "reason":result.get("reason")}))
    return 1 if result["status"].startswith("FAIL") else 0


if __name__=="__main__":
    raise SystemExit(main())
