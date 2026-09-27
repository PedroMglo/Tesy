#!/usr/bin/env python3
"""Execute the frozen P8 preload OFF/ON/OFF2 numeric boundary in fresh scopes."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from c2_gate import GateError, strict_json
from c3_compare_capture_logits import resources
from c7_timing_runner import cool_start

MODEL = "/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf"
BACKEND = "/home/pmglo/Projects/Tesy/tesy-scale-lab/backends/streaming"
ARMS = (("off1", "P8-preload-off", "tools/c7_profile_probe", True),
        ("on", "P8-preload-on-capture", "tools/c8_boundary_capture", False),
        ("off2", "P8-preload-off-repeat", "tools/c7_profile_probe", True))


def program_physical_consumed():
    total=0.0
    for path in Path("results").glob("c*/raw/*.json"):
        try:
            row=strict_json(path.read_text())
            if isinstance(row,dict) and isinstance(row.get("run_id"),str) and \
               isinstance(row.get("elapsed_s"),(int,float)):
                total+=row["elapsed_s"]
        except (OSError,ValueError):
            pass
    return total


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_stat():
    st=Path(MODEL).stat()
    return {"dev":st.st_dev,"inode":st.st_ino,"size_bytes":st.st_size,
            "mtime_ns":st.st_mtime_ns,"ctime_ns":st.st_ctime_ns}


def run_arm(root,label,variant,binary,off,commit,protocol):
    run_id="c8-g2-"+label
    stem=root/"raw"/run_id
    if any(Path(str(stem)+suffix).exists() for suffix in (".json",".stdout",".stderr",".samples.jsonl",".f32")) or \
       Path(str(stem)+".capture").exists():
        raise GateError("no-replace C8 arm exists")
    if model_stat()!=protocol["model_stat"] or program_physical_consumed()+330>16*3600:
        raise GateError("model identity or physical budget changed before arm")
    pre=cool_start(root,300)
    cmd=["systemd-run","--user","--scope","-p","MemoryMax=19327352832",
         "-p","MemorySwapMax=0","--","python3","tools/run_bounded.py",
         "--run-id",run_id,"--model-id","gpt-oss-120b-mxfp4-gguf",
         "--backend","streaming","--backend-root",BACKEND,
         "--output-root",str((root/"raw").resolve()),"--variant",variant,
         "--workload","results/c2-target-numeric-v1.ids",
         "--cache-condition","fresh-expert-pools-page-cache-uncontrolled",
         "--timeout-s","300","--max-rss-gib","16","--max-cgroup-gib","16.5",
         "--min-available-gib","6","--max-gpu-mib","6500",
         "--max-cpu-c","95","--max-gpu-c","80","--max-nvme-c","70",
         "--require-telemetry","--ready-marker",
         "C7_CONTEXT_READY" if off else "C8_CONTEXT_READY"]
    if off:cmd += ["--env","LLAMA_MOE_STREAM_NO_PRELOAD=1"]
    cmd += ["--",binary,MODEL,"results/c2-target-numeric-v1.ids"]
    if off:
        cmd += ["results/c3-p1-latency-ids01.tsv",str(stem),"--ngl","8","--case","log_medium"]
    else:
        cmd += [str(Path(str(stem)+".capture")),"--ngl","8"]
    env=os.environ.copy()
    for key in ("LLAMA_MOE_STREAM_NO_PRELOAD","TESY_CPU_FA_PREFILL_VEC_COMPAT","LD_PRELOAD"):
        env.pop(key,None)
    process=subprocess.run(cmd,text=True,capture_output=True,check=False,env=env)
    receipt={"run_id":run_id,"arm":label,"measurement_commit":commit,"pre_run":pre,
             "scope_returncode":process.returncode}
    try:
        path=Path(str(stem)+".json")
        manifest=strict_json(path.read_text())
        receipt.update(manifest_sha256=sha(path),elapsed_s=manifest["elapsed_s"],
                       maxima=manifest["maxima"],returncode=manifest["returncode"],
                       stop_reason=manifest["stop_reason"])
        if manifest["returncode"]!=0 or manifest["stop_reason"] is not None or process.returncode!=0 or \
           manifest["binary_sha256"]!=protocol["binary_sha256"][label] or \
           manifest["artifact_identity"]["stat_at_launch"]!=protocol["model_stat"] or \
           manifest["artifact_identity"]["stat_at_end"]!=protocol["model_stat"] or \
           manifest["mapped_backend_libraries_sha256"]!=protocol["mapped_backend_libraries_sha256"] or \
           not manifest["mapped_libraries_match_ldd"]:
            raise GateError("bounded process/identity failed")
        receipt["sample_count"]=resources(manifest,Path(str(stem)+".samples.jsonl"))
        receipt["status"]="PASS"
    except (OSError,ValueError,KeyError,TypeError,GateError) as exc:
        receipt.update(status="FAIL_RESOURCES_OR_EVIDENCE",reason=f"{type(exc).__name__}: {exc}",
                       systemd_stderr_tail=process.stderr[-500:])
    return receipt


def main():
    p=argparse.ArgumentParser()
    p.add_argument("root",type=Path)
    p.add_argument("measurement_commit")
    args=p.parse_args()
    root=args.root
    destination=root/"observer-runner.json"
    if destination.exists() or (root/"boundary-summary.json").exists():
        p.error("no-replace observer result exists")
    protocol=strict_json((root/"protocol.json").read_text())
    actual=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    dirty=subprocess.check_output(["git","status","--porcelain"],text=True).strip()
    if actual!=args.measurement_commit or dirty or model_stat()!=protocol["model_stat"] or \
       sha("results/c2-target-numeric-v1.ids")!=protocol["numeric_ids_sha256"] or \
       any(sha(binary)!=protocol["binary_sha256"][label] for label,_,binary,_ in ARMS):
        p.error("C8 observer identity differs from freeze")
    report={"schema":"c8-observer-runner-v1","measurement_commit":actual,
            "status":"PASS","physical_time_before_s":program_physical_consumed(),"arms":[]}
    for label,variant,binary,off in ARMS:
        try:arm=run_arm(root,label,variant,binary,off,actual,protocol)
        except (OSError,ValueError,KeyError,TypeError,GateError,subprocess.SubprocessError) as exc:
            arm={"arm":label,"status":"FAIL_RESOURCES_OR_EVIDENCE","reason":f"{type(exc).__name__}: {exc}"}
        report["arms"].append(arm)
        print(label,arm["status"],arm.get("elapsed_s"),flush=True)
        if arm["status"]!="PASS":
            report["status"]=arm["status"]
            break
        time.sleep(10)
    report["physical_time_after_s"]=program_physical_consumed()
    with destination.open("x") as f:
        json.dump(report,f,indent=2,sort_keys=True,allow_nan=False);f.write("\n")
    if report["status"]!="PASS":return 1
    gate=subprocess.run([sys.executable,"tools/c8_boundary_gate.py",str(root),
                         "--output",str(root/"boundary-summary.json")],
                        text=True,capture_output=True,check=False)
    print(gate.stdout.strip(),flush=True)
    if gate.stderr:print(gate.stderr[-1000:],file=sys.stderr)
    return gate.returncode


if __name__=="__main__":
    raise SystemExit(main())
