#!/usr/bin/env python3
"""Post-run integrity seal for local C3 raw capture files."""

import argparse
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path


def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as source:
        while block:=source.read(1024*1024):
            h.update(block)
    return h.hexdigest()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    if args.output.exists():
        raise SystemExit("no-replace seal output exists")
    root=Path(f"results/{args.run_id}.raw")
    manifest_path=Path(f"results/{args.run_id}.json")
    manifest=json.loads(manifest_path.read_text())
    if manifest["returncode"]!=0 or manifest["stop_reason"] is not None:
        raise SystemExit("source run failed")
    with (root/"index.tsv").open() as file:
        reader=csv.DictReader(file,delimiter="\t")
        if set(reader.fieldnames or [])!={"phase","layer","name","type","ne","nb","bytes","file"}:
            raise SystemExit("capture index schema changed")
        rows=list(reader)
    indexed={row["file"]:int(row["bytes"]) for row in rows}
    named=set(indexed)
    if len(named)!=len(rows):
        raise SystemExit("duplicate tensor filename")
    phases=(root/"phases.txt").read_text().splitlines()
    allowed=(named|{"index.tsv","byte_checks.tsv","stages.txt","phases.txt",
                    "route_prestate.tsv"}|
             {f"{phase}.logits.f32" for phase in phases})
    entries=[]
    total=0
    for path in sorted(root.iterdir(),key=lambda x:x.name):
        if not path.is_file() or path.is_symlink():
            raise SystemExit("nonregular or linked raw file")
        size=path.stat().st_size
        if path.name not in allowed:
            raise SystemExit("unindexed raw file")
        if path.name in named:
            if size!=indexed[path.name]:
                raise SystemExit("tensor file size differs from index")
            total+=size
        entries.append((path.name,size,digest(path)))
    if not named.issubset({x[0] for x in entries}) or total>256*2**20:
        raise SystemExit("missing tensor or payload cap exceeded")
    leaves=hashlib.sha256()
    for name,size,value in entries:
        leaves.update(f"{name}\0{size}\0{value}\n".encode())
    report={"schema":"c3-post-run-raw-seal-v1","classification":"POST_RUN_SEAL",
            "run_id":args.run_id,"sealed_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
            "manifest_sha256":digest(manifest_path),"index_sha256":digest(root/"index.tsv"),
            "file_count":len(entries),"tensor_rows":len(rows),"tensor_payload_bytes":total,
            "sorted_file_digest_sha256":leaves.hexdigest(),
            "analyzer_sha256":digest(Path(__file__))}
    with args.output.open("x") as out:
        json.dump(report,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({"run_id":args.run_id,"files":len(entries),
                      "payload_bytes":total,"digest":leaves.hexdigest()}))


if __name__=="__main__":
    main()
