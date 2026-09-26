#!/usr/bin/env python3
"""Measure localhost chat arrival latencies and actual templated prompt length."""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import time
from urllib.request import Request, urlopen

from c2_gate import GateError, strict_json
from run_bounded import sha256


ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:18367"


def post(path, payload, timeout=30):
    request = Request(BASE+path,data=json.dumps(payload).encode(),
                      headers={"Content-Type":"application/json"},method="POST")
    with urlopen(request,timeout=timeout) as response:
        return strict_json(response.read().decode())


def stream(prompt, model_id, cap):
    payload = {"model":model_id,"messages":[{"role":"user","content":prompt}],
               "max_tokens":cap,"temperature":0,"seed":42,"stream":True,
               "stream_options":{"include_usage":True}}
    request = Request(BASE+"/v1/chat/completions",data=json.dumps(payload).encode(),
                      headers={"Content-Type":"application/json"},method="POST")
    t0=time.monotonic()
    first_text=first_reasoning=first_final=None
    reasoning=[];final=[];usage=None;finish_reason=None;chunks=0;done=False
    with urlopen(request,timeout=900) as response:
        for raw in response:
            line=raw.decode(errors="replace").strip()
            if line=="data: [DONE]": done=True;break
            if not line.startswith("data: "): continue
            event=strict_json(line[6:]); chunks+=1
            if event.get("usage") is not None: usage=event["usage"]
            for choice in event.get("choices",[]):
                if choice.get("finish_reason") is not None: finish_reason=choice["finish_reason"]
                delta=choice.get("delta") or {}
                r=delta.get("reasoning_content") or ""
                f=delta.get("content") or ""
                if r:
                    reasoning.append(r)
                    if first_reasoning is None: first_reasoning=time.monotonic()-t0
                if f:
                    final.append(f)
                    if first_final is None: first_final=time.monotonic()-t0
                if (r or f) and first_text is None: first_text=time.monotonic()-t0
    if not done or finish_reason is None:
        raise GateError("stream ended without DONE or finish_reason")
    return {"first_text_chunk_s":first_text,"first_reasoning_chunk_s":first_reasoning,
            "first_final_chunk_s":first_final,"elapsed_s":time.monotonic()-t0,
            "chunk_events":chunks,"finish_reason":finish_reason,"usage":usage,
            "reasoning_text": "".join(reasoning),"final_text":"".join(final),
            "interpretation":"client text arrival; SSE chunks are not per-token intervals"}


def token_count(prompt, model_id):
    body={"model":model_id,"messages":[{"role":"user","content":prompt}],
          "max_tokens":512,"temperature":0,"seed":42}
    applied=post("/apply-template",body)
    if "prompt" not in applied:
        raise GateError("template response missing prompt")
    tokens=post("/tokenize",{"content":applied["prompt"],
                             "add_special":False,"parse_special":True})
    ids=tokens.get("tokens")
    if type(ids) is not list or any(type(x) is not int for x in ids):
        raise GateError("tokenizer response missing integer token IDs")
    return len(ids)


def atomic_json(path, value):
    if path.exists(): raise FileExistsError(path)
    descriptor,tmp=tempfile.mkstemp(prefix=".c2-latency-",dir=path.parent)
    try:
        with os.fdopen(descriptor,"w") as out:
            json.dump(value,out,indent=2,allow_nan=False);out.write("\n")
            out.flush();os.fsync(out.fileno())
        os.link(tmp,path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--workload",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--count-only",action="store_true")
    p.add_argument("--ids",nargs="*")
    args=p.parse_args()
    workload=strict_json(args.workload.read_text())
    if set(workload)!={"schema_version","tasks"} or workload["schema_version"]!="c2-latency-v1":
        raise GateError("wrong latency workload schema")
    tasks=workload["tasks"]
    if type(tasks) is not list or not tasks or any(set(x)!={"id","prompt","category"} for x in tasks):
        raise GateError("invalid latency task list")
    if len({x["id"] for x in tasks})!=len(tasks): raise GateError("duplicate latency task ID")
    if args.ids: tasks=[x for x in tasks if x["id"] in args.ids]
    if not tasks: raise GateError("no selected latency tasks")
    with urlopen(BASE+"/v1/models",timeout=10) as response:
        model_id=strict_json(response.read().decode())["data"][0]["id"]
    rows=[]
    for task in tasks:
        count=token_count(task["prompt"],model_id)
        if count+512>4096: raise GateError("prompt exceeds context with output reserve")
        result={"id":task["id"],"category":task["category"],"templated_prompt_tokens":count}
        if not args.count_only:
            result["stream"]=stream(task["prompt"],model_id,512)
        rows.append(result)
        print(json.dumps({"id":task["id"],"prompt_tokens":count,
                          "first_text_s":result.get("stream",{}).get("first_text_chunk_s")}),flush=True)
    output={"schema_version":"c2-latency-client-v1","created_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
            "workload_sha256":sha256(args.workload),"model_id_reported":model_id,
            "count_only":args.count_only,"policy":{"context":4096,"max_tokens":512,
                "temperature":0,"seed":42,"cache_reuse":"determined by server flags"},
            "rows":rows,"limitation":"SSE arrival is not per-token TPOT; separate monitored server manifest required for resources"}
    atomic_json(args.output,output)


if __name__=="__main__":
    main()
