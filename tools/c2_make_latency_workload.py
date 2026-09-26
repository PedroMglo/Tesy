#!/usr/bin/env python3
"""Deterministic synthetic incident prompts; token lengths are checked after Harmony template."""

import json
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"workloads/c2_latency_prompts.json"


def make(name, count):
    target=count//2
    lines=[]
    for i in range(count):
        severity="CRITICAL" if i==target else "low"
        state="OPEN" if i==target else "closed"
        lines.append(f"2026-09-26T12:{i:02d}:00Z ticket T{i:03d} service svc{i%7} severity {severity} state {state} owner team{i%5}.")
    prompt=("Audit these synthetic incident records. Exactly one ticket has severity CRITICAL "
            "and state OPEN. Return only a JSON object with one key, ticket, whose value is "
            "that ticket ID. Do not include a code fence.\n"+"\n".join(lines))
    return {"id":name,"category":"spec_log","prompt":prompt}


def main():
    tasks=[make("latency-short",2),make("latency-medium",18),make("latency-long",58)]
    with OUT.open("x") as out:
        json.dump({"schema_version":"c2-latency-v1","tasks":tasks},out,indent=2)
        out.write("\n")
    for item in tasks: print(item["id"],len(item["prompt"]))


if __name__=="__main__":main()
