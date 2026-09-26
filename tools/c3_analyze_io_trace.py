#!/usr/bin/env python3
"""Account P1 expert reads and cache tensor writes by layer and prompt chunk."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import re


WEIGHT=re.compile(r"^blk\.(\d+)\.ffn_(gate|up|down)_exps\.weight(?:\.stream_cache)?$")


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as source:
        while block:=source.read(1024*1024):h.update(block)
    return h.hexdigest()


def union_seconds(intervals):
    if not intervals:return 0.0
    ordered=sorted(intervals)
    total=0
    start,end=ordered[0]
    for a,b in ordered[1:]:
        if a>end:
            total+=end-start
            start,end=a,b
        else:end=max(end,b)
    return (total+end-start)/1e9


def analyze(run_id):
    prefix=Path(f"results/{run_id}")
    trace_path=Path(str(prefix)+".trace.tsv")
    chunks_path=Path(str(prefix)+".chunks.tsv")
    manifest_path=Path(str(prefix)+".json")
    inventory_path=Path("results/c3-r1-inventory01.jsonl")
    manifest=json.loads(manifest_path.read_text())
    if manifest["returncode"]!=0 or manifest["stop_reason"] is not None or \
       manifest["maxima"]["swap_bytes"]!=0:
        raise ValueError("source run failed/resource violation")
    chunks={}
    for row in csv.DictReader(chunks_path.open(),delimiter="\t"):
        chunk=int(row["chunk"])
        if chunk in chunks or int(row["count"])<1 or float(row["wall_s"])<=0:
            raise ValueError("duplicate/invalid chunk")
        chunks[chunk]={"case":row["case"],"start":int(row["start"]),
                       "count":int(row["count"]),"wall_s":float(row["wall_s"])}
    if not chunks or set(chunks)!=set(range(1,len(chunks)+1)):
        raise ValueError("chunk IDs incomplete")
    tensors=[]
    for line in inventory_path.read_text().splitlines():
        row=json.loads(line)
        if WEIGHT.fullmatch(row.get("name","")):
            start=row["data_offset"]
            tensors.append((start,start+row["n_bytes"],row["name"]))
    if len(tensors)!=108:
        raise ValueError("expert tensor inventory incomplete")
    with trace_path.open() as file:
        reader=csv.DictReader(file,delimiter="\t")
        if set(reader.fieldnames or [])!={"kind","phase","layer_or_offset","requested",
                                     "returned","start_ns","duration_ns","name"}:
            raise ValueError("trace schema changed")
        trace=list(reader)
    if not trace:
        raise ValueError("empty trace")
    marker={}
    grouped=defaultdict(lambda:{"read_calls":0,"read_requested_bytes":0,
                                "read_returned_bytes":0,"upload_calls":0,
                                "upload_requested_bytes":0,"read_intervals":[],
                                "upload_intervals":[]})
    named_counts=defaultdict(lambda:[0,0])
    for row in trace:
        kind=row["kind"]
        phase=int(row["phase"])
        start=int(row["start_ns"])
        duration=int(row["duration_ns"])
        requested=int(row["requested"])
        returned=int(row["returned"])
        if kind=="M":
            if phase>0:
                if phase not in chunks or phase in marker:
                    raise ValueError("unknown/duplicate trace phase start")
                marker[phase]=[start,None]
            else:
                active=[x for x,v in marker.items() if v[1] is None]
                if len(active)!=1:raise ValueError("trace phase end without unique start")
                marker[active[0]][1]=start
            continue
        if kind not in ("R","U") or phase not in chunks or \
           requested<1 or returned!=requested or duration<0:
            raise ValueError("invalid/incomplete read or upload")
        if kind=="R":
            offset=int(row["layer_or_offset"])
            overlaps=[(min(offset+requested,end)-max(offset,begin),name)
                      for begin,end,name in tensors if offset<end and offset+requested>begin]
            if not overlaps:
                raise ValueError("read offset outside canonical expert tensors")
            overlap,name=max(overlaps)
            if overlap<requested-8192:
                raise ValueError("read span not attributable to one tensor")
        else:
            name=row["name"].removesuffix(".stream_cache")
            if not WEIGHT.fullmatch(row["name"]):
                raise ValueError("upload target is not a stream cache tensor")
        layer=int(WEIGHT.fullmatch(name).group(1))
        key=(phase,layer)
        item=grouped[key]
        if kind=="R":
            item["read_calls"]+=1
            item["read_requested_bytes"]+=requested
            item["read_returned_bytes"]+=returned
            item["read_intervals"].append((start,start+duration))
            named_counts[(phase,name)][0]+=1
        else:
            item["upload_calls"]+=1
            item["upload_requested_bytes"]+=requested
            item["upload_intervals"].append((start,start+duration))
            named_counts[(phase,name)][1]+=1
    if set(marker)!=set(chunks) or any(end is None or end<=start for start,end in marker.values()):
        raise ValueError("trace markers do not cover every chunk")
    if any(r!=u for r,u in named_counts.values()):
        raise ValueError("read/upload tensor counts differ")
    for (phase,layer),item in grouped.items():
        begin,end=marker[phase]
        if any(a<begin or b>end for a,b in item["read_intervals"]+item["upload_intervals"]):
            raise ValueError("I/O event outside marked prompt chunk")
        item["read_union_s"]=union_seconds(item.pop("read_intervals"))
        item["upload_union_s"]=union_seconds(item.pop("upload_intervals"))
    rows=[]
    for phase in sorted(chunks):
        for layer in range(36):
            item=grouped.get((phase,layer))
            if item is None:
                item={"read_calls":0,"read_requested_bytes":0,"read_returned_bytes":0,
                      "upload_calls":0,"upload_requested_bytes":0,
                      "read_union_s":0.0,"upload_union_s":0.0}
            rows.append({"chunk":phase,"case":chunks[phase]["case"],"layer":layer,
                         "device":"cpu" if layer<29 else "gpu",**item})
    totals={}
    for phase in sorted(chunks):
        parts=[r for r in rows if r["chunk"]==phase]
        totals[str(phase)]={**chunks[phase],"layers_with_io":sum(r["read_calls"]>0 for r in parts),
                            "read_calls":sum(r["read_calls"] for r in parts),
                            "upload_calls":sum(r["upload_calls"] for r in parts),
                            "read_requested_bytes":sum(r["read_requested_bytes"] for r in parts),
                            "read_returned_bytes":sum(r["read_returned_bytes"] for r in parts),
                            "upload_requested_bytes":sum(r["upload_requested_bytes"] for r in parts)}
    return {"schema":"c3-io-trace-account-v1","status":"PASS","run_id":run_id,
            "classification":"INSTRUMENTED_DIAGNOSTIC",
            "limitations":"read bytes are syscall payload, upload bytes are requested API bytes; neither is exclusive physical traffic; interval unions overlap compute",
            "trace_events":len(trace),"chunks":totals,"layer_rows":rows,
            "source_sha256":{str(p):sha(p) for p in (trace_path,chunks_path,manifest_path,inventory_path)},
            "analyzer_sha256":sha(__file__)}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    try:report=analyze(args.run_id)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        report={"schema":"c3-io-trace-account-v1","status":"FAIL_EVIDENCE",
                "run_id":args.run_id,"reason":f"{type(exc).__name__}: {exc}"}
    with args.output.open("x") as out:
        json.dump(report,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({"status":report["status"],"trace_events":report.get("trace_events"),
                      "chunks":len(report.get("chunks",{})),"reason":report.get("reason")}))
    return 0 if report["status"]=="PASS" else 1


if __name__=="__main__":
    raise SystemExit(main())
