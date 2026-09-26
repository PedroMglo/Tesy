#!/usr/bin/env python3
"""Audit target consumer slices and witnessed physical slot generations."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path


HEADER={"phase","layer","wave","logical","slot","generation","tensor","bytes","status"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def analyze(run_id):
    manifest_path=Path(f"results/{run_id}.json")
    root=Path(f"results/{run_id}.raw")
    ledger_path=root/"byte_checks.tsv"
    manifest=json.loads(manifest_path.read_text())
    if manifest["returncode"]!=0 or manifest["stop_reason"] is not None:
        raise ValueError("target run failed")
    for group in ("events","events_local"):
        if any(manifest["cgroup_start"][group][event] !=
               manifest["cgroup_end"][group][event] for event in ("max","oom","oom_kill")):
            raise ValueError("cgroup event changed")
    if manifest["cgroup_end"]["swap_current"]!=0 or manifest["maxima"]["swap_bytes"]!=0:
        raise ValueError("runtime swap")
    with ledger_path.open() as file:
        reader=csv.DictReader(file,delimiter="\t")
        if set(reader.fieldnames or [])!=HEADER:
            raise ValueError("ledger schema changed")
        rows=list(reader)
    groups=defaultdict(set)
    events=defaultdict(list)
    total=0
    for row in rows:
        phase,layer,wave=row["phase"],int(row["layer"]),int(row["wave"])
        expert,slot,gen,kind=(int(row[k]) for k in ("logical","slot","generation","tensor"))
        size=int(row["bytes"])
        if row["status"]!="EQUAL" or not (0<=layer<36 and 0<=expert<128 and
             0<=slot<32 and gen>0 and 0<=kind<6 and
             size==(4406400 if kind<3 else 11520)):
            raise ValueError("invalid consumer slice")
        key=(phase,layer,wave,expert,slot,gen)
        if kind in groups[key]:
            raise ValueError("duplicate slice")
        groups[key].add(kind)
        total+=size
    if not groups or any(kinds!=set(range(6)) for kinds in groups.values()):
        raise ValueError("incomplete tensor set")
    for (phase,layer,wave,expert,slot,gen) in groups:
        if phase=="prefill0" and layer==0:
            events[slot].append((wave,gen,expert))
    rebound=[]
    for slot,history in events.items():
        history.sort()
        if len({expert for _,_,expert in history})>1:
            for (_,g1,e1),(_,g2,e2) in zip(history,history[1:]):
                if e1!=e2 and g2<=g1:
                    raise ValueError("expert rebind did not advance generation")
            rebound.append({"slot":slot,"history":history})
    if len(rebound)<1:
        raise ValueError("no generation reuse witness")
    return {"schema":"c3-generation-audit-v1","status":"PASS",
            "run_id":run_id,"slice_count":len(rows),"bytes_compared":total,
            "active_pairs":len(groups),"rebound_slots_layer0_prefill0":len(rebound),
            "example":rebound[0],"source_sha256":{
                str(manifest_path):sha(manifest_path),str(ledger_path):sha(ledger_path),
                str(root/"index.tsv"):sha(root/"index.tsv")},
            "analyzer_sha256":sha(__file__)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    try:
        result=analyze(args.run_id)
    except (ValueError,KeyError,OSError,TypeError) as exc:
        result={"schema":"c3-generation-audit-v1","status":"FAIL_EVIDENCE",
                "run_id":args.run_id,"reason":f"{type(exc).__name__}: {exc}"}
    with args.output.open("x") as out:
        json.dump(result,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({"status":result["status"],"slices":result.get("slice_count"),
                      "rebound_slots":result.get("rebound_slots_layer0_prefill0")}))
    return 0 if result["status"]=="PASS" else 1


if __name__=="__main__":
    raise SystemExit(main())
