#!/usr/bin/env python3
"""Blocking, monitored localhost launcher for the frozen 32-slot diagnostic profile."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

from c2_server_run import configuration
from c2_verify_artifact import verify
from c2_gate import GateError, strict_json


ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/"workloads/c2c_sustained32_protocol.json"
MODEL=Path("/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf")
SIZE=63387346208


def preflight():
    args=SimpleNamespace(model="target120b",suite="historic20",ngl=8,ubatch=32,
                         slots=32,protocol_id="c2c-sustained32-v1")
    current,config,_,model=configuration(args)
    frozen=strict_json(PROTOCOL.read_text())
    if current!=frozen:
        raise GateError("model, binary, libraries, flags or workload differ from frozen 32-slot identity")
    backend=ROOT/"backends/streaming"
    if subprocess.check_output(["git","-C",str(backend),"status","--porcelain"],text=True).strip():
        raise GateError("streaming backend worktree is dirty")
    artifact=verify(model,frozen["identity"]["model_sha256"],SIZE)
    return config["server_command"],artifact


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--run-id",required=True)
    args=p.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+",args.run_id):
        p.error("invalid run ID")
    command,artifact=preflight()
    print(json.dumps({"preflight":artifact,"backend_profile":"target120b GPU8 slots32",
                      "endpoint":"http://127.0.0.1:18367",
                      "server_policy":"medium template, context4096, parallel1, no prompt cache",
                      "client_must_send":"temperature=0, seed=42 and an explicit max_tokens cap for comparable requests"}),flush=True)
    wrapper=["systemd-run","--user","--scope","-p","MemoryMax=19327352832",
             "-p","MemorySwapMax=0","--",sys.executable,"tools/run_bounded.py",
             "--run-id",args.run_id,"--model-id","gpt-oss-120b-mxfp4-gguf",
             "--backend","streaming","--variant","c2-target32-local-server-diagnostic",
             "--workload","workloads/c2c_sustained32_protocol.json",
             "--cache-condition","fresh-process-no-prompt-cache-odirect-experts",
             "--timeout-s","3600","--max-rss-gib","17","--min-available-gib","6",
             "--max-gpu-mib","7000","--max-cpu-c","95","--max-gpu-c","80",
             "--max-nvme-c","70","--require-telemetry",
             "--env","LLAMA_MOE_STREAM_NO_PRELOAD=1","--",*command]
    os.chdir(ROOT)
    os.execvp("systemd-run",wrapper)


if __name__=="__main__":main()
