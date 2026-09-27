#!/usr/bin/env python3
"""Post-run SHA seal and read-back verification for the frozen C8 capture."""

import argparse
import datetime
import hashlib
import json
from pathlib import Path

from c2_gate import GateError, strict_json
from c7_boundary_gate import capture


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(root):
    capture_root=root/"raw/c8-g2-on.capture"
    _,coverage=capture(capture_root)
    files={p.name:sha(p) for p in sorted(capture_root.iterdir()) if p.is_file()}
    if len(files)!=3686:
        raise GateError("C8 capture file count changed")
    aggregate=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return files,coverage,aggregate


def seal(root,output):
    if output.exists():
        raise GateError("no-replace capture seal exists")
    boundary=strict_json((root/"boundary-summary.json").read_text())
    if boundary["status"]!="SAME_PROFILE_PASS":
        raise GateError("boundary gate not passed")
    files,coverage,aggregate=inventory(root)
    if coverage!=boundary["coverage"]:
        raise GateError("capture changed since observer gate")
    row={"schema":"c8-capture-postrun-seal-v1",
         "created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "evidence_class":"post-run SHA seal, not capture-time proof",
         "measurement_commit":"099e5ecad0975ce49597e80c072e2f5c5a71a057",
         "boundary_summary_sha256":sha(root/"boundary-summary.json"),
         "coverage":coverage,"file_count":len(files),"files_sha256":files,
         "aggregate_sha256":aggregate}
    with output.open("x") as f:json.dump(row,f,indent=2,sort_keys=True,allow_nan=False);f.write("\n")
    return row


def verify(root,seal_path):
    row=strict_json(seal_path.read_text())
    if row["schema"]!="c8-capture-postrun-seal-v1" or \
       row["boundary_summary_sha256"]!=sha(root/"boundary-summary.json"):
        raise GateError("capture seal identity changed")
    files,coverage,aggregate=inventory(root)
    if files!=row["files_sha256"] or coverage!=row["coverage"] or \
       aggregate!=row["aggregate_sha256"] or len(files)!=row["file_count"]:
        raise GateError("capture payload differs from post-run SHA seal")
    return row


def main():
    p=argparse.ArgumentParser()
    p.add_argument("root",type=Path)
    p.add_argument("mode",choices=("seal","verify"))
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    path=args.output or args.root/"capture-seal.json"
    try:
        row=seal(args.root,path) if args.mode=="seal" else verify(args.root,path)
    except (OSError,KeyError,ValueError,TypeError,GateError) as exc:
        print(f"FAIL_RESOURCES_OR_EVIDENCE: {type(exc).__name__}: {exc}")
        return 1
    print(json.dumps({"status":"PASS","file_count":row["file_count"],
                      "aggregate_sha256":row["aggregate_sha256"]}))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
