#!/usr/bin/env python3
"""Six sequential bounded arms for the repaired C3 P2B prefill A/B."""

import json
from pathlib import Path
import subprocess
import sys

MODEL = "/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf"
IDS = "results/c3-p1-latency-ids01.tsv"
SCHEDULE = ((1,"off"),(1,"on"),(2,"on"),(2,"off"),(3,"off"),(3,"on"))
PREFIX = "c3-p2b-ab"


def main():
    for pair,arm in SCHEDULE:
        run_id=f"{PREFIX}-p{pair}-{arm}01"
        for suffix in (".json",".stdout",".stderr",".samples.jsonl",
                       ".f32",".rows.tsv",".chunks.tsv"):
            if Path("results",run_id+suffix).exists():
                raise SystemExit(f"no-replace output already exists: {run_id+suffix}")
    for pair,arm in SCHEDULE:
        run_id=f"{PREFIX}-p{pair}-{arm}01"
        command=["systemd-run","--user","--scope","--property=MemoryMax=18G",
                 "--property=MemorySwapMax=0","python3","tools/run_bounded.py",
                 "--run-id",run_id,"--model-id","gpt-oss-120b-mxfp4-gguf",
                 "--backend","streaming","--variant",f"c3-p2-ab-{arm}-gpu8-slot32-ub32",
                 "--workload",IDS,"--cache-condition",
                 "fresh-process-expert-cache-cold-page-cache-uncontrolled",
                 "--timeout-s","1000","--max-rss-gib","17","--min-available-gib","6",
                 "--max-gpu-mib","7000","--max-cpu-c","95","--max-gpu-c","80",
                 "--max-nvme-c","70","--require-telemetry"]
        if arm=="off":
            command += ["--env","LLAMA_MOE_STREAM_NO_PRELOAD=1"]
        command += ["--","tools/c3_prefill_probe",MODEL,IDS,
                    f"results/{run_id}","all"]
        print(f"START {run_id}",flush=True)
        result=subprocess.run(command,check=False)
        if result.returncode:
            print(f"FAIL_RUN {run_id} exit={result.returncode}",flush=True)
            return 1
        manifest=json.loads(Path("results",run_id+".json").read_text())
        if manifest["returncode"]!=0 or manifest["stop_reason"] is not None or \
           manifest["cgroup_end"]["swap_current"]!=0:
            print(f"FAIL_EVIDENCE {run_id}",flush=True)
            return 1
        print(f"END {run_id} elapsed_s={manifest['elapsed_s']:.3f}",flush=True)
    return 0


if __name__=="__main__":
    sys.exit(main())
