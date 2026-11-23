#!/usr/bin/env python3
"""Cross-check pre-remap cache classes against post-remap consumer witnesses."""

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    root=Path(f"results/{args.run_id}.raw")
    pre_path=root/"route_prestate.tsv"
    post_path=root/"byte_checks.tsv"
    manifest_path=Path(f"results/{args.run_id}.json")
    status="PASS"
    reason=None
    counts={}
    try:
        manifest=json.loads(manifest_path.read_text())
        if manifest["returncode"]!=0 or manifest["stop_reason"] is not None or \
           manifest["cgroup_end"]["swap_current"]!=0:
            raise ValueError("target run failed/resource violation")
        with pre_path.open() as file:
            pre=list(csv.DictReader(file,delimiter="\t"))
        with post_path.open() as file:
            post=list(csv.DictReader(file,delimiter="\t"))
        if len(pre)!=8 or len({(x["phase"],x["layer"],x["expert"]) for x in pre})!=8:
            raise ValueError("prestate rows incomplete/duplicated")
        after={}
        for x in post:
            if x["phase"]=="decode0" and x["tensor"]=="0":
                key=(x["layer"],x["logical"])
                if key in after:
                    raise ValueError("duplicate post-remap logical expert")
                after[key]=(int(x["slot"]),int(x["generation"]))
        if len(after)!=8:
            raise ValueError("post-remap rows incomplete")
        for x in pre:
            if x["phase"]!="decode0" or (x["layer"],x["expert"]) not in after:
                raise ValueError("prestate identity differs from consumer")
            cls=x["class"]
            if cls not in ("READY","IN_FLIGHT","ABSENT_COLD","ABSENT_RELOAD"):
                raise ValueError("invalid class")
            slot,gen=after[x["layer"],x["expert"]]
            if cls=="READY" and (int(x["slot"]),int(x["generation"]))!=(slot,gen):
                raise ValueError("ready hit changed slot/generation before consumption")
            if cls.startswith("ABSENT") and (int(x["slot"]),int(x["generation"]))!=(-1,0):
                raise ValueError("absent expert had a mapped slot")
            if gen<1:
                raise ValueError("expert was not loaded before consumption")
        counts=dict(Counter(x["class"] for x in pre))
        if not all(counts.get(k,0)>0 for k in ("READY","ABSENT_COLD","ABSENT_RELOAD")):
            raise ValueError("required ready/cold/reload classes not all observed")
    except (OSError,ValueError,KeyError,TypeError) as exc:
        status="FAIL_EVIDENCE"
        reason=f"{type(exc).__name__}: {exc}"
    report={"schema":"c3-prestate-audit-v1","status":status,"run_id":args.run_id,
            "classes":counts,"reason":reason,"source_sha256":{
                str(path):sha(path) for path in (manifest_path,pre_path,post_path) if path.exists()},
            "analyzer_sha256":sha(__file__)}
    with args.output.open("x") as out:
        json.dump(report,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({"status":status,"classes":counts,"reason":reason}))
    return 0 if status=="PASS" else 1


if __name__=="__main__":
    raise SystemExit(main())
