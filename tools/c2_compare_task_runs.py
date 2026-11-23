#!/usr/bin/env python3
"""Compare paired frozen C2 task outcomes without causal parameter-count claims."""

import argparse
import json
from pathlib import Path

from c2_gate import GateError, strict_json
from c2_server_run import CORE_IDS, EVAL12_IDS
from run_bounded import sha256


def compare(stock_grade, target_grade, stock_raw, target_raw):
    grades=[strict_json(Path(p).read_text()) for p in (stock_grade,target_grade)]
    raw=[strict_json(Path(p).read_text()) for p in (stock_raw,target_raw)]
    suites=[x["preflight"]["config"]["suite"] for x in raw]
    if len(set(suites))!=1 or suites[0] not in ("c2core8","c2eval12"):
        raise GateError("paired runs use different or unsupported C2 suites")
    expected=list(CORE_IDS if suites[0]=="c2core8" else EVAL12_IDS)
    for i in range(2):
        if grades[i]["schema_version"]!="c2-task-grade-v2" or \
           [x["task_id"] for x in grades[i]["scores"]]!=expected or \
           [x["id"] for x in raw[i]["results"]]!=expected or \
           raw[i]["stop_reasons"] or raw[i]["returncode"]!=0:
            raise GateError("incomplete or mismatched C2 run/grade")
        if grades[i]["source_run"]!=str((stock_raw,target_raw)[i]):
            raise GateError("grade does not name paired raw manifest")
    identities=[x["preflight"]["protocol"]["identity"] for x in raw]
    if identities[0]["workload_sha256"]!=identities[1]["workload_sha256"] or \
       identities[0]["input_sha256"]!=identities[1]["input_sha256"]:
        raise GateError("task workload identity differs")
    outcomes=[]
    counts={"both_pass":0,"both_fail":0,"target_only":0,"stock_only":0}
    for i,task_id in enumerate(expected):
        stock=grades[0]["scores"][i];target=grades[1]["scores"][i]
        a=stock["status"]=="PASS";b=target["status"]=="PASS"
        label="both_pass" if a and b else "target_only" if b else "stock_only" if a else "both_fail"
        counts[label]+=1
        outcomes.append({"id":task_id,"outcome":label,
                         "stock_status":stock["status"],"target_status":target["status"],
                         "stock_wall_s":stock["request_wall_s"],"target_wall_s":target["request_wall_s"],
                         "stock_completion_tokens":stock["completion_tokens_total"],
                         "target_completion_tokens":target["completion_tokens_total"],
                         "stock_finish_reason":stock["finish_reason"],
                         "target_finish_reason":target["finish_reason"]})
    total=lambda rows:sum(x["request_wall_s"] for x in rows)
    return {"schema_version":"c2-task-comparison-v1","suite":suites[0],"n":len(expected),"counts":counts,
            "stock_pass":grades[0]["pass_count"],"target_pass":grades[1]["pass_count"],
            "stock_total_request_wall_s":total(grades[0]["scores"]),
            "target_total_request_wall_s":total(grades[1]["scores"]),
            "tasks":outcomes,
            "source_sha256":{str(path):sha256(path) for path in
                             (stock_grade,target_grade,stock_raw,target_raw)},
            "identity":{"stock":identities[0],"target":identities[1]},
            "limitations":["frozen small task pilot selected before responses; no significance claim",
                           "different model/tokenizer/backend/placement; no parameter-count causal attribution",
                           "target production-placement numeric parity remains blocked by C2-B",
                           "TTFT and reasoning/final token split unavailable in these nonstreamed task runs"]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--stock-grade",required=True,type=Path)
    p.add_argument("--target-grade",required=True,type=Path)
    p.add_argument("--stock-run",required=True,type=Path)
    p.add_argument("--target-run",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    report=compare(a.stock_grade,a.target_grade,a.stock_run,a.target_run)
    with open(a.output,"x") as out:
        json.dump(report,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({k:report[k] for k in ("counts","stock_pass","target_pass",
                                            "stock_total_request_wall_s","target_total_request_wall_s")}))


if __name__=="__main__":main()
