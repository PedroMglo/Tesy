#!/usr/bin/env python3
"""Grade the two selected C2 failure follow-ups under a new C3 cap."""

import argparse
import hashlib
import json
from pathlib import Path

from c2_gate import strict_json
from c2_task_grade import grade_text
from c2_server_run import C3_FOLLOWUP_IDS


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--run-id",required=True)
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    stem=Path("results")/args.run_id
    raw_path=Path(str(stem)+".json")
    norm_path=Path(str(stem)+".normalized.json")
    raw=strict_json(raw_path.read_text())
    norm=strict_json(norm_path.read_text())
    preflight=raw["preflight"]
    config=preflight["config"]
    if preflight["run_id"]!=args.run_id or config["suite"]!="c3followup2" or \
       config["request_policy"]["max_tokens"]!=3072 or \
       preflight["protocol"]["campaign_id"]!="tesy-c3-20260926" or \
       preflight["protocol"]["expected_request_ids"]!=list(C3_FOLLOWUP_IDS) or \
       raw["stop_reasons"] or raw["returncode"]!=0 or \
       norm["run_id"]!=args.run_id or norm["outcome"]["stop_reasons"] or \
       [x["id"] for x in raw["results"]]!=list(C3_FOLLOWUP_IDS) or \
       [x["id"] for x in norm["requests"]]!=list(C3_FOLLOWUP_IDS):
        raise ValueError("follow-up run identity/completeness failed")
    rows=[]
    for item in raw["results"]:
        task_id=item["id"]
        outcome=grade_text(task_id,(item["message"] or {}).get("content"))
        if outcome["status"]=="VALIDATOR_ENV_ERROR":
            raise RuntimeError("isolated grader unavailable")
        usage=item["usage"]
        if type(usage["prompt_tokens"]) is not int or type(usage["completion_tokens"]) is not int or \
           usage["prompt_tokens"]+3072>4096 or not 0<usage["completion_tokens"]<=3072:
            raise ValueError("usage/context/output reserve invalid")
        status=outcome["status"] if item["finish_reason"]=="stop" else "FAIL_TRUNCATED"
        rows.append({"task_id":task_id,"status":status,"finish_reason":item["finish_reason"],
                     "prompt_tokens":usage["prompt_tokens"],
                     "completion_tokens_total":usage["completion_tokens"],
                     "wall_s":item["ended_s"]-item["started_s"],
                     "reasoning_characters":len((item["message"] or {}).get("reasoning_content") or ""),
                     "final_characters":len((item["message"] or {}).get("content") or ""),
                     "detail":outcome})
    report={"schema":"c3-selected-cap-followup-v1","status":"PASS_EVIDENCE",
            "run_id":args.run_id,"selection":"post-C2-failure diagnostic, not held-out",
            "max_output_tokens":3072,"context_configured":4096,"rows":rows,
            "pass_count":sum(row["status"]=="PASS" for row in rows),
            "source_sha256":{str(path):sha(path) for path in (raw_path,norm_path)},
            "grader_sha256":sha(__file__)}
    with args.output.open("x") as out:
        json.dump(report,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({"status":report["status"],"pass_count":report["pass_count"],
                      "rows":[(r["task_id"],r["status"]) for r in rows]}))


if __name__=="__main__":
    raise SystemExit(main())
