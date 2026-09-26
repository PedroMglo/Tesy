#!/usr/bin/env python3
"""Stop only the lab-owned localhost server identified by an active bounded run."""

import argparse
import json
import os
from pathlib import Path
import signal
import time

from c2_gate import GateError, strict_json


ROOT=Path(__file__).resolve().parents[1]


def stop(run_id, model_path, dry_run=False):
    if not run_id.replace("-","").replace("_","").isalnum():
        raise GateError("invalid run ID")
    sample_path=ROOT/"results"/(run_id+".samples.jsonl")
    samples=sample_path.read_text().splitlines()
    if not samples: raise GateError("no active run samples")
    sample=strict_json(samples[-1])
    pid=sample.get("pid")
    if type(pid) is not int or pid<=1: raise GateError("invalid sampled PID")
    live=Path(f"/proc/{pid}")
    argv=(live/"cmdline").read_bytes().split(b"\0")
    args=[x.decode(errors="replace") for x in argv if x]
    if not args or Path(args[0]).name!="llama-server" or \
       "-m" not in args or args[args.index("-m")+1]!=str(Path(model_path).resolve()) or \
       "--host" not in args or args[args.index("--host")+1]!="127.0.0.1" or \
       "--port" not in args or args[args.index("--port")+1]!="18367":
        raise GateError("PID does not identify expected local llama-server")
    if os.getsid(pid)!=pid:
        raise GateError("server is not its own process group leader")
    cgroup=(live/"cgroup").read_text()
    if sample["cgroup"]["path"] not in cgroup:
        raise GateError("PID cgroup differs from sampled run")
    if dry_run:
        return {"status":"VERIFIED_ONLY","run_id":run_id,"pid":pid,"cgroup":sample["cgroup"]["path"]}
    os.killpg(pid,signal.SIGTERM)
    for _ in range(100):
        if not live.exists(): break
        time.sleep(0.1)
    return {"status":"SIGTERM_SENT","run_id":run_id,"pid":pid,
            "process_gone":not live.exists()}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("run_id")
    p.add_argument("--model-path",required=True)
    p.add_argument("--dry-run",action="store_true")
    a=p.parse_args()
    print(json.dumps(stop(a.run_id,a.model_path,a.dry_run)))


if __name__=="__main__":main()
