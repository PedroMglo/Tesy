#!/usr/bin/env python3
"""Freeze exact server-templated C2-D prompt IDs for C3 prefill diagnostics."""

import hashlib
import json
from pathlib import Path
import time
from urllib.error import URLError
from urllib.request import Request,urlopen

from c2_gate import strict_json


BASE="http://127.0.0.1:18367"
MODEL="/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf"
SOURCE=Path("workloads/c2_latency_prompts.json")
OUTPUT=Path("results/c3-p1-latency-ids01.json")
EXPECTED={"latency-short":113,"latency-medium":496,"latency-long":1522}


def post(path,payload):
    request=Request(BASE+path,data=json.dumps(payload).encode(),
                    headers={"Content-Type":"application/json"},method="POST")
    with urlopen(request,timeout=30) as response:
        return strict_json(response.read().decode())


def main():
    if OUTPUT.exists():
        raise SystemExit("no-replace token ID file exists")
    source_bytes=SOURCE.read_bytes()
    source=strict_json(source_bytes.decode())
    tasks=source["tasks"]
    if [x["id"] for x in tasks]!=list(EXPECTED):
        raise ValueError("C2-D task order changed")
    deadline=time.monotonic()+90
    while True:
        try:
            with urlopen(BASE+"/health",timeout=3) as response:
                if response.status==200:break
        except (URLError,TimeoutError):
            pass
        if time.monotonic()>deadline:
            raise TimeoutError("localhost server not ready")
        time.sleep(0.5)
    rows=[]
    for task in tasks:
        request={"model":MODEL,"messages":[{"role":"user","content":task["prompt"]}],
                 "max_tokens":512,"temperature":0,"seed":42}
        applied=post("/apply-template",request)
        rendered=applied.get("prompt")
        if type(rendered) is not str or not rendered:
            raise ValueError("template result missing")
        tokenized=post("/tokenize",{"content":rendered,"add_special":False,
                                    "parse_special":True})
        ids=tokenized.get("tokens")
        if type(ids) is not list or any(type(x) is not int or x<0 for x in ids) or \
           len(ids)!=EXPECTED[task["id"]] or len(ids)+512>4096:
            raise ValueError("official template/tokenizer count differs from C2-D")
        rows.append({"id":task["id"],"prompt_sha256":hashlib.sha256(task["prompt"].encode()).hexdigest(),
                     "rendered_sha256":hashlib.sha256(rendered.encode()).hexdigest(),
                     "token_count":len(ids),"ids":ids})
    result={"schema":"c3-p1-latency-ids-v1","server_run_id":"c3-p1-tokenize-server01",
            "source_sha256":hashlib.sha256(source_bytes).hexdigest(),
            "model_sha256":"582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d",
            "template_policy":"server official medium GPT-OSS Harmony via /apply-template",
            "tokenizer_policy":"server /tokenize add_special=false parse_special=true",
            "rows":rows}
    with OUTPUT.open("x") as out:
        json.dump(result,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({"status":"PASS","source_sha256":result["source_sha256"],
                      "token_counts":[x["token_count"] for x in rows]}))


if __name__=="__main__":
    main()
