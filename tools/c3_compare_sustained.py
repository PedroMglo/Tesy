#!/usr/bin/env python3
"""Check C3 preload server against the frozen C2 output and C3 resource gate."""

import argparse
import hashlib
import json
from pathlib import Path

from c2_gate import strict_json

BASE = "c2c-target32-sustained01"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(name,suffix):
    path=Path("results")/(name+suffix)
    return strict_json(path.read_text())


def compare(run_id):
    baseline=read(BASE,".json")
    candidate=read(run_id,".json")
    gate=read(run_id,".gate.json")
    published=read(run_id,".published.json")
    analysis=read(run_id,"-analysis01.json")
    if gate["status"]!="PASS" or published["status"]!="PASS" or \
       analysis["combined_status"]!="PASS" or \
       candidate["preflight"]["config"]["suite"]!="c3sustained20" or \
       candidate["preflight"]["config"]["preload_enabled"] is not True or \
       candidate["preflight"]["config"]["explicit_env"] or \
       candidate["preflight"]["protocol"]["campaign_id"]!="tesy-c3-20260926" or \
       baseline["preflight"]["config"]["suite"]!="historic20" or \
       baseline["preflight"]["config"]["explicit_env"] != \
           {"LLAMA_MOE_STREAM_NO_PRELOAD":"1"}:
        raise ValueError("sustained source/setting/gate invalid")
    if published["source_sha256"].get(f"results/{run_id}.json") != \
       sha(Path("results")/(run_id+".json")):
        raise ValueError("published raw checksum mismatch")
    for key in ("model_sha256","backend_sha","binary_sha256","library_sha256"):
        if baseline["preflight"]["protocol"]["identity"][key] != \
           candidate["preflight"]["protocol"]["identity"][key]:
            raise ValueError(f"{key} changed")
    if baseline["preflight"]["protocol"]["identity"]["workload_sha256"] != \
       candidate["preflight"]["protocol"]["identity"]["workload_sha256"]:
        raise ValueError("workload differs")
    old_config=baseline["preflight"]["config"]
    new_config=candidate["preflight"]["config"]
    for key in ("server_command","request_policy","task_ids"):
        if old_config[key]!=new_config[key]:
            raise ValueError(f"server {key} changed")
    a,b=baseline["results"],candidate["results"]
    if len(a)!=20 or len(b)!=20 or [x["id"] for x in a] != [x["id"] for x in b]:
        raise ValueError("twenty request identities/order incomplete")
    differences=[]
    rows=[]
    for old,new in zip(a,b):
        changed=[]
        for key in ("finish_reason",):
            if old[key]!=new[key]: changed.append(key)
        for key in ("prompt_tokens","completion_tokens"):
            if old["usage"][key]!=new["usage"][key]: changed.append(key)
        for key in ("content","reasoning_content"):
            if (old["message"] or {}).get(key) != (new["message"] or {}).get(key):
                changed.append(key)
        if changed: differences.append({"id":new["id"],"fields":changed})
        rows.append({"id":new["id"],"base_wall_s":old["ended_s"]-old["started_s"],
                     "preload_wall_s":new["ended_s"]-new["started_s"],
                     "base_finish":old["finish_reason"],
                     "preload_finish":new["finish_reason"],
                     "completion_tokens":new["usage"]["completion_tokens"]})
    return {"schema":"c3-preload-sustained-comparison-v1",
            "status":"PASS_SCOPED" if not differences else "FAIL_OUTPUT_MISMATCH",
            "run_id":run_id,"historical_control_run_id":BASE,
            "exact_greedy_message_usage_matches":len(rows)-len(differences),
            "expected_requests":20,"differences":differences,"rows":rows,
            "candidate_decode_tok_s":analysis["whole"]["decode_tok_s"],
            "candidate_last_half_tok_s":analysis["last_ten"]["decode_tok_s"],
            "candidate_prefill_s":analysis["whole"]["prefill_s"],
            "candidate_process_elapsed_s":analysis["process_elapsed_s"],
            "candidate_cgroup_peak_bytes":candidate["cgroup_end"]["memory_peak"],
            "source_sha256":{str(path):sha(path) for path in (
                Path("results")/(BASE+".json"),Path("results")/(run_id+".json"),
                Path("results")/(run_id+".gate.json"),
                Path("results")/(run_id+".published.json"),
                Path("results")/(run_id+"-analysis01.json"))},
            "analyzer_sha256":sha(__file__)}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("run_id")
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    try: result=compare(args.run_id)
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
        result={"schema":"c3-preload-sustained-comparison-v1",
                "status":"FAIL_EVIDENCE","run_id":args.run_id,
                "reason":f"{type(exc).__name__}: {exc}"}
    with args.output.open("x") as out:
        json.dump(result,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({"status":result["status"],
                      "matches":result.get("exact_greedy_message_usage_matches"),
                      "decode_tok_s":result.get("candidate_decode_tok_s"),
                      "reason":result.get("reason")}))
    return 0 if result["status"]=="PASS_SCOPED" else 1


if __name__=="__main__":
    raise SystemExit(main())
