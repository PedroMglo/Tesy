#!/usr/bin/env python3
"""Bounded three-turn synthetic chat with measured context growth and no truncation."""

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

from c2_gate import GateError, strict_json
from c2_latency_client import atomic_json, post


BASE="http://127.0.0.1:18367"
KEY="K-731"


def rows(n):
    return "\n".join(f"synthetic audit row {i:03d}: service svc{i%9}, counter {i*3}, status OK." for i in range(n))


QUESTIONS=[
    f"Remember this synthetic session key: {KEY}. Reply with exactly JSON {{\"ack\":true}}.",
    f"Additional unrelated records:\n{rows(30)}\nWhat session key did I ask you to remember? Reply only JSON with key session_key.",
    f"More unrelated records follow; keep the whole conversation in context:\n{rows(80)}\nWhat original session key did I give you? Reply only JSON with key session_key.",
]


def count(messages, model):
    body={"model":model,"messages":messages,"max_tokens":256,"temperature":0,"seed":42}
    template=post("/apply-template",body)
    tokens=post("/tokenize",{"content":template["prompt"],"add_special":False,"parse_special":True})["tokens"]
    return len(tokens)


def request(messages,model):
    body={"model":model,"messages":messages,"max_tokens":256,"temperature":0,"seed":42,"stream":False}
    req=Request(BASE+"/v1/chat/completions",data=json.dumps(body).encode(),
                headers={"Content-Type":"application/json"},method="POST")
    t0=time.monotonic()
    with urlopen(req,timeout=900) as response:
        doc=strict_json(response.read().decode())
    elapsed=time.monotonic()-t0
    choices=doc.get("choices")
    if type(choices) is not list or len(choices)!=1:
        raise GateError("missing one completion choice")
    return doc,choices[0],elapsed


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    with urlopen(BASE+"/v1/models",timeout=10) as response:
        model=strict_json(response.read().decode())["data"][0]["id"]
    messages=[];results=[]
    for i,prompt in enumerate(QUESTIONS):
        messages.append({"role":"user","content":prompt})
        token_count=count(messages,model)
        if token_count+256>4096:raise GateError("multiturn context exceeds reserved window")
        doc,choice,elapsed=request(messages,model)
        answer=choice.get("message") or {}
        final=answer.get("content") or ""
        try:
            parsed=strict_json(final)
            expected={"ack":True} if i==0 else {"session_key":KEY}
            valid=parsed==expected and type(parsed) is dict
        except ValueError:
            valid=False
        usage=doc.get("usage") or {}
        row={"turn":i+1,"templated_prompt_tokens":token_count,
             "api_prompt_tokens":usage.get("prompt_tokens"),
             "api_completion_tokens":usage.get("completion_tokens"),
             "cached_prompt_tokens":(usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
             "finish_reason":choice.get("finish_reason"),"request_wall_s":elapsed,
             "final_valid":valid,"final_text":final,
             "reasoning_text":answer.get("reasoning_content") or ""}
        results.append(row)
        if choice.get("finish_reason")!="stop":raise GateError(f"turn {i+1} truncated or stopped unexpectedly")
        messages.append({"role":"assistant","content":final})
        print(json.dumps({"turn":i+1,"prompt_tokens":usage.get("prompt_tokens"),
                          "finish_reason":row["finish_reason"],"valid":valid}),flush=True)
    api_counts=[x["api_prompt_tokens"] for x in results]
    if any(type(x) is not int for x in api_counts) or api_counts!=sorted(api_counts) or \
       len(set(api_counts))!=3 or any(x["cached_prompt_tokens"]!=0 for x in results):
        raise GateError("context did not grow monotonically or prefix cache reused")
    result={"schema_version":"c2-multiturn-v1","created_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
            "model_id_reported":model,"policy":{"context":4096,"max_tokens":256,
             "temperature":0,"seed":42,"turns":3,"prompt_cache":False},
            "questions_sha256":hashlib.sha256(json.dumps(QUESTIONS,ensure_ascii=False,
                separators=(",",":")).encode()).hexdigest(),
            "results":results,"all_final_valid":all(x["final_valid"] for x in results),
            "scope":"actual API prompt counts; no context-shift or truncation is accepted"}
    atomic_json(a.output,result)


if __name__=="__main__":main()
