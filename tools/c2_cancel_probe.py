#!/usr/bin/env python3
"""Close one local streamed request, then verify that a bounded follow-up completes."""

import argparse
import datetime as dt
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

from c2_gate import GateError, strict_json
from c2_latency_client import BASE, atomic_json


def send(model, prompt, cap, stream):
    body={"model":model,"messages":[{"role":"user","content":prompt}],
          "max_tokens":cap,"temperature":0,"seed":42,"stream":stream}
    return urlopen(Request(BASE+"/v1/chat/completions",data=json.dumps(body).encode(),
                           headers={"Content-Type":"application/json"},method="POST"),timeout=300)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    with urlopen(BASE+"/v1/models",timeout=10) as response:
        model=strict_json(response.read().decode())["data"][0]["id"]
    t0=time.monotonic();seen_text=False;chunks=0
    with send(model,"Continue a numbered list of synthetic audit items up to 500. Begin at 1.",512,True) as response:
        for raw in response:
            line=raw.decode(errors="replace").strip()
            if not line.startswith("data: ") or line=="data: [DONE]": continue
            event=strict_json(line[6:]);chunks+=1
            for choice in event.get("choices",[]):
                delta=choice.get("delta") or {}
                if delta.get("content") or delta.get("reasoning_content"):
                    seen_text=True;break
            if seen_text:break
    canceled_at=time.monotonic()-t0
    if not seen_text:raise GateError("stream ended before nonempty text; cancel not exercised")
    t1=time.monotonic()
    with send(model,"What is 7+5? Reply with the number only.",64,False) as response:
        doc=strict_json(response.read().decode())
    choices=doc.get("choices")
    if type(choices) is not list or len(choices)!=1 or choices[0].get("finish_reason")!="stop":
        raise GateError("follow-up after cancellation did not complete")
    answer=(choices[0].get("message") or {}).get("content") or ""
    result={"schema_version":"c2-cancel-probe-v1","created_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
            "model_id_reported":model,"cancel_after_first_nonempty_text":True,
            "cancel_chunks_seen":chunks,"cancel_elapsed_s":canceled_at,
            "followup_elapsed_s":time.monotonic()-t1,"followup_finish_reason":"stop",
            "followup_final_text":answer,"followup_usage":doc.get("usage"),
            "limitation":"client connection closed; server log required to confirm backend canceled the task"}
    atomic_json(a.output,result)
    print(json.dumps({"cancel_chunks_seen":chunks,"cancel_elapsed_s":canceled_at,
                      "followup_final_text":answer}),flush=True)


if __name__=="__main__":main()
