#!/usr/bin/env python3
"""Atomically publish a no-replace local checksum manifest for one C2 server run."""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import tempfile

from c2_gate import GateError, strict_json
from run_bounded import sha256


ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = (".preflight.json", ".json", ".normalized.json", ".stdout",
            ".stderr", ".samples.jsonl", ".gate.json")


def publish(run_id, protocol):
    protocol = protocol.resolve()
    if not protocol.is_relative_to(ROOT):
        raise GateError("protocol outside lab")
    if not run_id.replace("-", "").replace("_", "").isalnum():
        raise GateError("invalid run ID")
    stem = ROOT / "results" / run_id
    files = {suffix:Path(str(stem)+suffix) for suffix in SUFFIXES}
    if not files[".preflight.json"].is_file() or not files[".json"].is_file():
        raise GateError("preflight or raw result missing")
    preflight = strict_json(files[".preflight.json"].read_text())
    raw = strict_json(files[".json"].read_text())
    if preflight["run_id"] != run_id or raw["preflight"]["run_id"] != run_id:
        raise GateError("run ID mismatch")
    if sha256(protocol) != preflight["protocol_sha256"]:
        raise GateError("protocol changed since preflight")
    for suffix in (".stdout", ".stderr", ".samples.jsonl"):
        if raw["source_sha256"].get(suffix) != sha256(files[suffix]):
            raise GateError(f"raw file changed: {suffix}")
    gate = strict_json(files[".gate.json"].read_text()) if files[".gate.json"].exists() else None
    if gate and gate["status"] == "PASS":
        if not files[".normalized.json"].is_file():
            raise GateError("PASS gate but normalized run missing")
        if gate["source_sha256"] != sha256(files[".normalized.json"]) or \
           gate["protocol_sha256"] != sha256(protocol):
            raise GateError("PASS gate source/protocol hash mismatch")
    hashes = {str(path.relative_to(ROOT)):sha256(path) for path in files.values() if path.exists()}
    hashes[str(protocol.relative_to(ROOT))] = sha256(protocol)
    start_cg = preflight.get("cgroup_start")
    end_cg = raw.get("cgroup_end")
    end_resource_ok = bool(start_cg and end_cg and end_cg.get("swap_current") == 0 and
                           end_cg.get("memory_peak") is not None and end_cg.get("memory_max") is not None and
                           end_cg["memory_peak"] <= end_cg["memory_max"] and
                           all(end_cg[group].get(key) == start_cg[group].get(key)
                               for group in ("events","events_local")
                               for key in ("max","oom","oom_kill")))
    report = {"schema_version":"c2-server-publication-v1","run_id":run_id,
              "published_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
              "status":"FAIL_END_RESOURCE" if not end_resource_ok else gate["status"] if gate else "NO_GATE",
              "end_resource_ok":end_resource_ok,
              "gate_reason":gate.get("reason") if gate else None,
              "raw_stop_reasons":raw["stop_reasons"],
              "lab_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
              "source_sha256":hashes,"publication":"local; no replacement of existing result"}
    final = Path(str(stem)+".published.json")
    if final.exists():
        raise FileExistsError(final)
    descriptor,temp = tempfile.mkstemp(prefix=f".{run_id}.publication-",dir=final.parent)
    try:
        with os.fdopen(descriptor,"w") as out:
            json.dump(report,out,indent=2,allow_nan=False);out.write("\n")
            out.flush();os.fsync(out.fileno())
        os.link(temp,final)  # atomic no-replace on the same filesystem
        dirfd = os.open(final.parent,os.O_RDONLY)
        try: os.fsync(dirfd)
        finally: os.close(dirfd)
    finally:
        Path(temp).unlink(missing_ok=True)
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("run_id")
    p.add_argument("--protocol",required=True,type=Path)
    args=p.parse_args()
    print(json.dumps(publish(args.run_id,args.protocol),allow_nan=False))


if __name__ == "__main__":
    main()
