#!/usr/bin/env python3
"""Launch frozen alternating P8/P12 pairs in bounded fresh processes."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from c2_gate import GateError, strict_json
from c7_timing_gate import ids_for, inspect

MODEL = "/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf"
BACKEND = "/home/pmglo/Projects/Tesy/tesy-scale-lab/backends/streaming"
ORDER = (("P8","P12"),("P12","P8"))
CASES = {"screen113":("g3","latency-short",113,300),
         "screen496":("g4","latency-medium",496,600)}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def physical_consumed():
    elapsed=0.0
    for pattern in ("results/c7-*/raw/*.json","results/c7b-*/raw/*.json",
                    "results/c7c-*/raw/*.json"):
        for path in Path(".").glob(pattern):
            try:
                row=strict_json(path.read_text())
                if isinstance(row,dict) and isinstance(row.get("elapsed_s"),(int,float)):
                    elapsed+=row["elapsed_s"]
            except (OSError,ValueError):
                pass
    return elapsed


def nvme_stat():
    result={}
    for item in sorted(Path("/sys/block").glob("nvme*n*")):
        path=item/"stat"
        if path.is_file():
            result[item.name]=[int(x) for x in path.read_text().split()]
    return result


def cool_start(root,timeout):
    if physical_consumed()+timeout+30 > 16*3600:
        raise GateError("global physical-time budget insufficient for next arm")
    for attempt in range(25):
        available=next(int(line.split()[1])*1024 for line in Path("/proc/meminfo").read_text().splitlines()
                       if line.startswith("MemAvailable:"))
        if available<6*2**30 or shutil.disk_usage(root).free<21*2**30:
            raise GateError("host RAM/disk precondition failed")
        if Path("/sys/class/power_supply/AC0/online").read_text().strip()!="1":
            raise GateError("AC power condition changed")
        output=subprocess.check_output(
            ["nvidia-smi","--query-gpu=memory.used,temperature.gpu,driver_version",
             "--format=csv,noheader,nounits"],text=True,timeout=10).strip()
        gpu_used,gpu_c,driver=[x.strip() for x in output.split(",")]
        sensors=json.loads(subprocess.check_output(["sensors","-j"],text=True,timeout=10))
        cpu_c=float(sensors["k10temp-pci-00c3"]["Tctl"]["temp1_input"])
        nvme_c=float(sensors["nvme-pci-c100"]["Composite"]["temp1_input"])
        state={"mem_available_bytes":available,"gpu_idle_mib":float(gpu_used),
               "gpu_c":float(gpu_c),"driver":driver,"cpu_c":cpu_c,"nvme_c":nvme_c}
        if state["gpu_idle_mib"]>500 or driver!="615.71.09":
            raise GateError("GPU allocation/driver changed before arm")
        if cpu_c<=75 and float(gpu_c)<=60 and nvme_c<=60:
            return state
        print("thermal_recovery",attempt+1,state,flush=True)
        time.sleep(5)
    raise GateError("thermal recovery precondition timed out at 120 s")


def launch(root,mode,commit,profile,pair):
    gate,case,count,timeout=CASES[mode]
    run_id=f"c7c-{gate}-pair{pair}-{profile.lower()}"
    stem=root/"raw"/run_id
    if any(Path(str(stem)+suffix).exists() for suffix in (".json",".stdout",".stderr",".samples.jsonl",
                                                           ".f32",".ops.tsv",".steps.tsv")):
        raise GateError("no-replace timing run already exists")
    protocol=strict_json((root/"timing-protocol.json").read_text())
    pre=cool_start(root,timeout)
    before=nvme_stat()
    cmd=["systemd-run","--user","--scope","-p","MemoryMax=19327352832",
         "-p","MemorySwapMax=0","--","python3","tools/run_bounded.py",
         "--run-id",run_id,"--model-id","gpt-oss-120b-mxfp4-gguf",
         "--backend","streaming","--backend-root",BACKEND,
         "--output-root",str((root/"raw").resolve()),
         "--variant",profile+"-timing-"+case,
         "--workload","results/c3-p1-latency-ids01.tsv",
         "--cache-condition","fresh-expert-pools-page-cache-uncontrolled",
         "--timeout-s",str(timeout),"--max-rss-gib","16","--max-cgroup-gib","16.5",
         "--min-available-gib","6","--max-gpu-mib","6500",
         "--max-cpu-c","95","--max-gpu-c","80","--max-nvme-c","70",
         "--require-telemetry","--ready-marker","C7_CONTEXT_READY",
         "--env","LLAMA_MOE_STREAM_NO_PRELOAD=1","--",
         "tools/c7_profile_probe",MODEL,"results/c2-target-numeric-v1.ids",
         "results/c3-p1-latency-ids01.tsv",str(stem),
         "--ngl","8" if profile=="P8" else "12","--case",case]
    process=subprocess.run(cmd,text=True,capture_output=True,check=False)
    after=nvme_stat()
    receipt={"run_id":run_id,"profile":profile,"pair":pair,"measurement_commit":commit,
             "pre_run":pre,"scope_returncode":process.returncode,
             "global_nvme_before":before,"global_nvme_after":after,
             "global_nvme_interpretation":"aggregate host counters; concurrent activity uncontrolled"}
    with Path(str(stem)+".host.json").open("x") as f:
        json.dump(receipt,f,indent=2,sort_keys=True);f.write("\n")
    try:
        prompt,continuation=ids_for(case)
        seal,_=inspect(root,run_id,profile,case,count,commit,prompt,continuation,protocol)
        receipt.update(status="PASS",manifest_sha256=seal["manifest_sha256"],
                       elapsed_s=seal["elapsed_s"],work_s=seal["work_s"],
                       maxima=seal["maxima"])
    except (OSError,ValueError,KeyError,TypeError,GateError) as exc:
        receipt.update(status="FAIL_RESOURCES_OR_EVIDENCE",
                       reason=f"{type(exc).__name__}: {exc}",
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
        p.error("no-replace timing result exists")
    actual=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    dirty=subprocess.check_output(["git","status","--porcelain"],text=True).strip()
    protocol=strict_json((root/"timing-protocol.json").read_text())
    if actual!=args.measurement_commit or dirty or sha("tools/c7_profile_probe")!=protocol["binary_sha256"] or \
       sha("tools/c7_timing_gate.py")!=protocol["analyzer_sha256"]:
        p.error("timing measurement identity differs from freeze")
    if strict_json((root/"bridge-summary.json").read_text())["status"]!="P8_BRIDGE_PASS" or \
       strict_json(Path("results/c7b-20260927T1206Z/reference-complete.json").read_text())["status"]!="SAME_PROFILE_ROUTED_LAYER_PASS":
        p.error("P8 bridge or P12 fidelity precondition absent")
    report={"schema":"c7c-timing-runner-v1","mode":args.mode,"measurement_commit":args.measurement_commit,
            "status":"PASS","arms":[],"physical_time_before_s":physical_consumed()}
    for pair,order in enumerate(ORDER,1):
        for profile in order:
            try:
                arm=launch(root,args.mode,args.measurement_commit,profile,pair)
            except (OSError,ValueError,KeyError,TypeError,GateError,
                    subprocess.SubprocessError) as exc:
                arm={"pair":pair,"profile":profile,"status":"FAIL_RESOURCES_OR_EVIDENCE",
                     "reason":f"{type(exc).__name__}: {exc}"}
            report["arms"].append(arm)
            print(f"pair={pair} profile={profile} status={arm['status']} work={arm.get('work_s')}",flush=True)
            if arm["status"]!="PASS":
                report["status"]=arm["status"]
                break
            time.sleep(10)  # fixed GPU/thermal settle before the next preflight
        if report["status"]!="PASS":
            break
    report["physical_time_after_s"]=physical_consumed()
    with destination.open("x") as f:
        json.dump(report,f,indent=2,sort_keys=True,allow_nan=False);f.write("\n")
    if report["status"]!="PASS":
        return 1
    output=root/("timing-pairs-"+suffix+".json")
    gate=subprocess.run([sys.executable,"tools/c7_timing_gate.py",str(root),args.mode,
                         args.measurement_commit,"--output",str(output)],
                        text=True,capture_output=True,check=False)
    print(gate.stdout.strip(),flush=True)
    return gate.returncode


if __name__=="__main__":
    sys.exit(main())
