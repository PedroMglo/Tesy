#!/usr/bin/env python3
"""Apply the prospective three-pair C3 prefill criterion without rounding."""

import argparse
import hashlib
import json
from pathlib import Path
import statistics

from c2_gate import strict_json


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    files=[Path(f"results/c3-p2-ab-p{n}-comparison01.json") for n in (1,2,3)]
    pairs=[strict_json(path.read_text()) for path in files]
    for n,pair in enumerate(pairs,1):
        if pair.get("status")!="PASS_SCREEN_NUMERIC_RESOURCE" or \
           pair.get("control_run_id")!=f"c3-p2-ab-p{n}-off01" or \
           pair.get("candidate_run_id")!=f"c3-p2-ab-p{n}-on01" or \
           [x["case"] for x in pair["cases"]]!=[
               "latency-short","latency-medium","latency-long"]:
            raise ValueError(f"pair {n} failed or changed identity/schedule")
    rows=[]
    for idx,case in enumerate(("latency-short","latency-medium","latency-long")):
        controls=[pair["cases"][idx]["control"]["wall_s"] for pair in pairs]
        candidates=[pair["cases"][idx]["candidate"]["wall_s"] for pair in pairs]
        reductions=[1-b/a for a,b in zip(controls,candidates)]
        med=statistics.median(reductions)
        within=max((max(controls)-min(controls))/statistics.median(controls),
                   (max(candidates)-min(candidates))/statistics.median(candidates))
        rows.append({"case":case,"control_s":controls,"candidate_s":candidates,
                     "paired_reduction_fraction":reductions,"median_reduction_fraction":med,
                     "within_arm_range_fraction":within,
                     "all_pairs_faster":all(x>0 for x in reductions),
                     "reproducible_beyond_range":all(x>0 for x in reductions) and med>within})
    medium,long=rows[1:]
    result={"schema":"c3-preload-ab-summary-v1","status":"PASS_EVIDENCE",
            "order":["p1:off-on","p2:on-off","p3:off-on"],"cases":rows,
            "reproducible_smaller_gain":all(x["reproducible_beyond_range"] for x in (medium,long)),
            "goal_25pct_prefill":all(x["reproducible_beyond_range"] and
                                      x["median_reduction_fraction"]>=0.25
                                      for x in (medium,long)),
            "decode_gate":"NOT_RUN","sustained_gate":"NOT_RUN",
            "source_sha256":{str(p):sha(p) for p in files},
            "analyzer_sha256":sha(__file__)}
    with args.output.open("x") as out:
        json.dump(result,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({"status":result["status"],
                      "reproducible":result["reproducible_smaller_gain"],
                      "goal25":result["goal_25pct_prefill"],
                      "median":[x["median_reduction_fraction"] for x in rows]}))


if __name__=="__main__":
    raise SystemExit(main())
