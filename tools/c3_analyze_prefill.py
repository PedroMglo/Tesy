#!/usr/bin/env python3
"""Pair C3 P1 no-trace and trace prefill probes without rounding gates."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re


PATTERNS={
    "access":re.compile(r"remap calls = (\d+), expert hits = (\d+), misses = (\d+) \((\d+) cold\)"),
    "load":re.compile(r"load stall = ([0-9.]+) ms"),
    "waves":re.compile(r"waves = (\d+) \((\d+) non-empty\), preloads issued = (\d+) \(ready on arrival = (\d+)\), wave stall = ([0-9.]+) ms"),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stats(path):
    text=Path(path).read_text()
    blocks=re.findall(r"C3_STATS_BEGIN (\S+) (\d+)\n(.*?)C3_STATS_END \1 \2",text,re.S)
    if not blocks:
        raise ValueError("backend stats markers missing")
    out=[]
    prior=None
    for name,chunk,body in blocks:
        match={key:pattern.search(body) for key,pattern in PATTERNS.items()}
        if not all(match.values()):
            raise ValueError("backend stat field missing")
        a=match["access"].groups(); w=match["waves"].groups()
        cumulative={"remap_calls":int(a[0]),"hits":int(a[1]),"misses":int(a[2]),
                    "cold":int(a[3]),"load_stall_ms":float(match["load"].group(1)),
                    "wave_calls":int(w[0]),"nonempty_waves":int(w[1]),
                    "preload_issued":int(w[2]),"resident_on_arrival":int(w[3]),
                    "wave_stall_ms":float(w[4])}
        delta={k:v-(prior[k] if prior else 0) for k,v in cumulative.items()}
        if any(v<0 for v in delta.values()):
            raise ValueError("backend counters decreased")
        out.append({"case":name,"chunk":int(chunk),"counters":delta})
        prior=cumulative
    return out


def chunks(path):
    rows=[]
    for row in csv.DictReader(Path(path).open(),delimiter="\t"):
        rows.append({"case":row["case"],"chunk":int(row["chunk"]),
                     "start":int(row["start"]),"count":int(row["count"]),
                     "wall_s":float(row["wall_s"])})
    if not rows or [x["chunk"] for x in rows]!=list(range(1,len(rows)+1)):
        raise ValueError("chunk rows incomplete")
    return rows


def analyze(off_id,trace_id,account_path):
    off=Path(f"results/{off_id}");trace=Path(f"results/{trace_id}")
    manifests=[json.loads(Path(str(p)+".json").read_text()) for p in (off,trace)]
    for m in manifests:
        if m["returncode"]!=0 or m["stop_reason"] is not None or \
           m["cgroup_end"]["swap_current"]!=0:
            raise ValueError("source run failed/resource violation")
    for key in ("model_id","backend_sha","workload_sha256"):
        if manifests[0][key]!=manifests[1][key]:
            raise ValueError("paired identity differs")
    left,right=(chunks(str(p)+".chunks.tsv") for p in (off,trace))
    if [(x["case"],x["chunk"],x["start"],x["count"]) for x in left]!=[
       (x["case"],x["chunk"],x["start"],x["count"]) for x in right]:
        raise ValueError("chunk schedule differs")
    stats_left,stats_right=(stats(str(p)+".stderr") for p in (off,trace))
    if len(stats_left)!=len(left) or len(stats_right)!=len(left):
        raise ValueError("backend stat rows incomplete")
    timing_keys={"load_stall_ms","wave_stall_ms"}
    for a,b in zip(stats_left,stats_right):
        if a["case"]!=b["case"] or a["chunk"]!=b["chunk"] or \
           any(a["counters"][key]!=b["counters"][key] for key in a["counters"]
               if key not in timing_keys):
            raise ValueError("backend access counters changed under tracing")
    logits_off=Path(str(off)+".f32");logits_trace=Path(str(trace)+".f32")
    if logits_off.read_bytes()!=logits_trace.read_bytes():
        raise ValueError("final prompt logits differ")
    if Path(str(off)+".rows.tsv").read_bytes()!=Path(str(trace)+".rows.tsv").read_bytes():
        raise ValueError("final prompt row identities differ")
    account=json.loads(account_path.read_text())
    if account["status"]!="PASS" or account["run_id"]!=trace_id:
        raise ValueError("trace accounting failed")
    rows=[]
    for index,(a,b,stat) in enumerate(zip(left,right,stats_left)):
        if (a["case"],a["chunk"])!=(stat["case"],stat["chunk"]):
            raise ValueError("stat/chunk identity differs")
        io=account["chunks"][str(a["chunk"])]
        if io["read_calls"]!=3*stat["counters"]["misses"] or \
           io["upload_calls"]!=3*stat["counters"]["misses"] or \
           io["upload_requested_bytes"]!=13219200*stat["counters"]["misses"]:
            raise ValueError("expert miss/read/upload accounting mismatch")
        rows.append({"case":a["case"],"chunk":a["chunk"],"start":a["start"],
                     "tokens":a["count"],"off_wall_s":a["wall_s"],
                     "trace_wall_s":b["wall_s"],"trace_overhead_pct":
                     100*(b["wall_s"]/a["wall_s"]-1),
                     "backend_off":stat["counters"],
                     "backend_trace":stats_right[index]["counters"],"io":io})
    return {"schema":"c3-prefill-pair-v1","status":"PASS",
            "off_run_id":off_id,"trace_run_id":trace_id,
            "final_logits_bitwise_equal":True,"rows":rows,
            "source_sha256":{str(path):sha(path) for path in (
                Path(str(off)+".json"),Path(str(trace)+".json"),
                Path(str(off)+".f32"),Path(str(trace)+".f32"),
                Path(str(off)+".chunks.tsv"),Path(str(trace)+".chunks.tsv"),
                account_path)},
            "analyzer_sha256":sha(__file__)}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("off_run_id")
    ap.add_argument("trace_run_id")
    ap.add_argument("--account",type=Path)
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    account=args.account or Path(f"results/{args.trace_run_id}-account.json")
    try:result=analyze(args.off_run_id,args.trace_run_id,account)
    except (ValueError,OSError,KeyError,TypeError) as exc:
        result={"schema":"c3-prefill-pair-v1","status":"FAIL_EVIDENCE",
                "reason":f"{type(exc).__name__}: {exc}"}
    with args.output.open("x") as out:
        json.dump(result,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({"status":result["status"],"rows":len(result.get("rows",[])),
                      "reason":result.get("reason")}))
    return 0 if result["status"]=="PASS" else 1


if __name__=="__main__":
    raise SystemExit(main())
