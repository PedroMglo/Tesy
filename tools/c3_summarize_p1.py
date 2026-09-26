#!/usr/bin/env python3
"""Compact C3 P1 case-level accounting from the validated diagnostic pair."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path


PAIR=Path("results/c3-p1-prefill-all-pair01.json")
ACCOUNT=Path("results/c3-p1-prefill-all-trace01-account-v2.json")
OUTPUT=Path("results/c3-p1-summary01.json")


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    pair=json.loads(PAIR.read_text());account=json.loads(ACCOUNT.read_text())
    if pair["status"]!="PASS" or account["status"]!="PASS" or \
       not pair["final_logits_bitwise_equal"]:
        raise ValueError("source pair/account failed")
    by_case=defaultdict(list)
    for row in pair["rows"]:by_case[row["case"]].append(row)
    cases=[]
    for case in ("latency-short","latency-medium","latency-long"):
        rows=by_case[case]
        if not rows:raise ValueError("case missing")
        layer=defaultdict(lambda:{"read_bytes":0,"upload_bytes":0,"read_calls":0})
        for item in account["layer_rows"]:
            if item["case"]==case:
                current=layer[item["layer"]]
                current["read_bytes"]+=item["read_returned_bytes"]
                current["upload_bytes"]+=item["upload_requested_bytes"]
                current["read_calls"]+=item["read_calls"]
        if len(layer)!=36:raise ValueError("layer accounting incomplete")
        seconds=sum(x["off_wall_s"] for x in rows)
        traced=sum(x["trace_wall_s"] for x in rows)
        tokens=sum(x["tokens"] for x in rows)
        misses=sum(x["backend_off"]["misses"] for x in rows)
        read_bytes=sum(x["io"]["read_returned_bytes"] for x in rows)
        upload_bytes=sum(x["io"]["upload_requested_bytes"] for x in rows)
        if read_bytes!=sum(x["read_bytes"] for x in layer.values()) or \
           upload_bytes!=sum(x["upload_bytes"] for x in layer.values()):
            raise ValueError("case/layer bytes differ")
        cases.append({"case":case,"prompt_tokens":tokens,"chunks":len(rows),
                      "untraced_prefill_s":seconds,"traced_prefill_s":traced,
                      "observed_trace_time_delta_pct":100*(traced/seconds-1),
                      "untraced_prefill_tok_s":tokens/seconds,
                      "backend_hits":sum(x["backend_off"]["hits"] for x in rows),
                      "backend_misses":misses,
                      "backend_cold_misses":sum(x["backend_off"]["cold"] for x in rows),
                      "backend_wave_stall_s":sum(x["backend_off"]["wave_stall_ms"] for x in rows)/1000,
                      "backend_load_stall_s":sum(x["backend_off"]["load_stall_ms"] for x in rows)/1000,
                      "read_requested_bytes":sum(x["io"]["read_requested_bytes"] for x in rows),
                      "read_returned_bytes":read_bytes,
                      "upload_requested_bytes":upload_bytes,
                      "read_returned_bytes_per_prompt_token":read_bytes/tokens,
                      "cpu_layers_read_bytes":sum(x["read_bytes"] for key,x in layer.items() if key<29),
                      "gpu_layers_read_bytes":sum(x["read_bytes"] for key,x in layer.items() if key>=29),
                      "top_read_layers":[{"layer":key,**value} for key,value in
                         sorted(layer.items(),key=lambda kv:kv[1]["read_bytes"],reverse=True)[:5]]})
    result={"schema":"c3-p1-case-summary-v1","status":"PASS",
            "classification":"INSTRUMENTED_DIAGNOSTIC_AND_UNTRACED_TIMING",
            "cases":cases,"limitations":{
                "read_bytes":"pread syscall bytes returned, not exclusive physical NVMe traffic",
                "upload_bytes":"ggml_backend_tensor_set requested bytes, not physical PCIe traffic; CPU copies included",
                "wave_wait":"backend blocked time in wave callbacks, not exclusive share of wall time",
                "trace_delta":"one ordered pair, includes thermal/cache dispersion and logging cost",
                "decode":"not measured by this prefill-only probe"},
            "source_sha256":{str(PAIR):sha(PAIR),str(ACCOUNT):sha(ACCOUNT)},
            "analyzer_sha256":sha(Path(__file__))}
    with OUTPUT.open("x") as out:json.dump(result,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({"status":result["status"],"cases":[(x["case"],x["untraced_prefill_s"])
                                                       for x in cases]}))


if __name__=="__main__":main()
