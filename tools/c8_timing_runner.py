#!/usr/bin/env python3
"""Launch frozen alternating P8 preload OFF/ON pairs in fresh bounded scopes."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from c2_gate import GateError, strict_json
from c7_timing_runner import cool_start, nvme_stat
from c8_observer_runner import model_stat, program_physical_consumed
from c8_timing_gate import CASES, ORDER, ids_for, inspect
from run_bounded import relevant_environment

MODEL="/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf"
BACKEND="/home/pmglo/Projects/Tesy/tesy-scale-lab/backends/streaming"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def launch(root,mode,commit,arm,pair,protocol):
    case,count,gate=CASES[mode]
    timeout=300 if mode=="screen113" else 600
    run_id=f"c8-{gate}-pair{pair}-{arm}"
    stem=root/"raw"/run_id
    if any(Path(str(stem)+suffix).exists() for suffix in
           (".json",".stdout",".stderr",".samples.jsonl",".f32",".ops.tsv",".steps.tsv")):
        raise GateError("no-replace C8 timing run exists")
    if model_stat()!=protocol["model_stat"] or program_physical_consumed()+timeout+30>16*3600:
        raise GateError("model identity or physical budget changed before C8 arm")
    pre=cool_start(root,timeout)
    before=nvme_stat()
    cmd=["systemd-run","--user","--scope","-p","MemoryMax=19327352832",
         "-p","MemorySwapMax=0","--","python3","tools/run_bounded.py",
         "--run-id",run_id,"--model-id","gpt-oss-120b-mxfp4-gguf",
         "--backend","streaming","--backend-root",BACKEND,
         "--output-root",str((root/"raw").resolve()),
         "--variant","P8-preload-"+arm+"-timing-"+case,
         "--workload","results/c3-p1-latency-ids01.tsv",
         "--cache-condition","fresh-expert-pools-page-cache-uncontrolled",
         "--timeout-s",str(timeout),"--max-rss-gib","16","--max-cgroup-gib","16.5",
         "--min-available-gib","6","--max-gpu-mib","6500",
         "--max-cpu-c","95","--max-gpu-c","80","--max-nvme-c","70",
         "--require-telemetry","--ready-marker","C7_CONTEXT_READY"]
    if arm=="off":cmd += ["--env","LLAMA_MOE_STREAM_NO_PRELOAD=1"]
    cmd += ["--","tools/c7_profile_probe",MODEL,"results/c2-target-numeric-v1.ids",
            "results/c3-p1-latency-ids01.tsv",str(stem),"--ngl","8","--case",case]
    env=os.environ.copy()
    for key in ("LLAMA_MOE_STREAM_NO_PRELOAD","TESY_CPU_FA_PREFILL_VEC_COMPAT","LD_PRELOAD"):
        env.pop(key,None)
    if relevant_environment(env):
        raise GateError("unfrozen relevant environment before C8 timing arm")
    process=subprocess.run(cmd,text=True,capture_output=True,check=False,env=env)
    after=nvme_stat()
    host={"run_id":run_id,"arm":arm,"pair":pair,"measurement_commit":commit,
          "pre_run":pre,"scope_returncode":process.returncode,
          "global_nvme_before":before,"global_nvme_after":after,
          "global_nvme_interpretation":"aggregate host counters; concurrent activity uncontrolled"}
    with Path(str(stem)+".host.json").open("x") as f:
        json.dump(host,f,indent=2,sort_keys=True);f.write("\n")
    receipt={k:host[k] for k in ("run_id","arm","pair","measurement_commit","pre_run","scope_returncode")}
    try:
        prompt,continuation=ids_for(case)
        seal,_=inspect(root,run_id,arm,case,count,commit,prompt,continuation,protocol)
        receipt.update(status="PASS",raw_manifest_sha256=seal["raw_manifest_sha256"],
                       elapsed_s=seal["elapsed_s"],work_s=seal["work_s"],maxima=seal["maxima"])
    except (OSError,ValueError,KeyError,TypeError,GateError) as exc:
        receipt.update(status="FAIL_RESOURCES_OR_EVIDENCE",reason=f"{type(exc).__name__}: {exc}",
                       systemd_stderr_tail=process.stderr[-500:])
    if process.returncode!=0 and receipt["status"]=="PASS":
        receipt.update(status="FAIL_RESOURCES_OR_EVIDENCE",
                       reason="scope exit nonzero despite parsed arm")
    return receipt


def main():
    p=argparse.ArgumentParser()
    p.add_argument("root",type=Path)
    p.add_argument("mode",choices=CASES)
    p.add_argument("measurement_commit")
    args=p.parse_args()
    root=args.root
    suffix="113" if args.mode=="screen113" else "496"
    destination=root/("timing-runner-"+suffix+".json")
    if destination.exists() or (root/("timing-pairs-"+suffix+".json")).exists():
        p.error("no-replace C8 timing result exists")
    actual=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    dirty=subprocess.check_output(["git","status","--porcelain"],text=True).strip()
    protocol=strict_json((root/"timing-protocol.json").read_text())
    if actual!=args.measurement_commit or dirty or model_stat()!=protocol["model_stat"] or \
       sha("tools/c7_profile_probe")!=protocol["binary_sha256"] or \
       sha("tools/c8_timing_gate.py")!=protocol["analyzer_sha256"] or \
       sha("tools/c8_timing_runner.py")!=protocol["runner_sha256"] or \
       sha(root/"reference-complete.json")!=protocol["reference_complete_sha256"]:
        p.error("C8 timing identity differs from freeze")
    if strict_json((root/"reference-complete.json").read_text())["status"]!="SAME_PROFILE_ROUTED_LAYER_PASS":
        p.error("C8 numerical prerequisite not passed")
    report={"schema":"c8-p8-preload-timing-runner-v1","mode":args.mode,
            "measurement_commit":actual,"status":"PASS","arms":[],
            "physical_time_before_s":program_physical_consumed()}
    for pair,order in enumerate(ORDER,1):
        for arm in order:
            try:row=launch(root,args.mode,actual,arm,pair,protocol)
            except (OSError,ValueError,KeyError,TypeError,GateError,
                    subprocess.SubprocessError) as exc:
                row={"pair":pair,"arm":arm,"status":"FAIL_RESOURCES_OR_EVIDENCE",
                     "reason":f"{type(exc).__name__}: {exc}"}
            report["arms"].append(row)
            print(f"pair={pair} arm={arm} status={row['status']} work={row.get('work_s')}",flush=True)
            if row["status"]!="PASS":
                report["status"]=row["status"]
                break
            time.sleep(10)
        if report["status"]!="PASS":break
    report["physical_time_after_s"]=program_physical_consumed()
    with destination.open("x") as f:
        json.dump(report,f,indent=2,sort_keys=True,allow_nan=False);f.write("\n")
    if report["status"]!="PASS":return 1
    output=root/("timing-pairs-"+suffix+".json")
    gate=subprocess.run([sys.executable,"tools/c8_timing_gate.py",str(root),args.mode,
                         args.measurement_commit,"--output",str(output)],
                        text=True,capture_output=True,check=False)
    print(gate.stdout.strip(),flush=True)
    if gate.stderr:print(gate.stderr[-1000:],file=sys.stderr)
    return gate.returncode


if __name__=="__main__":
    raise SystemExit(main())
