#!/usr/bin/env python3
"""Fail-closed numeric/resource gate and exploratory prefill comparison."""

import argparse
import hashlib
import json
from pathlib import Path

from c2_gate import strict_json
from c3_analyze_prefill import chunks, stats
from c3_compare_capture_logits import resources

CASES = ("latency-short", "latency-medium", "latency-long")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def analyze(control_id, candidate_id):
    paths = [Path("results") / run_id for run_id in (control_id, candidate_id)]
    manifests = [strict_json(Path(str(p)+".json").read_text()) for p in paths]
    for path, manifest in zip(paths, manifests):
        resources(manifest, Path(str(path)+".samples.jsonl"))
    for key in ("model_id", "backend_sha", "backend_libraries_sha256",
                "binary_sha256", "workload_sha256"):
        if manifests[0][key] != manifests[1][key]:
            raise ValueError(f"{key} differs")
    if manifests[0]["explicit_env"].get("LLAMA_MOE_STREAM_NO_PRELOAD") != "1" or \
       "LLAMA_MOE_STREAM_NO_PRELOAD" in manifests[1]["explicit_env"]:
        raise ValueError("control/candidate preload identity invalid")
    row_files = [Path(str(p)+".rows.tsv") for p in paths]
    if row_files[0].read_bytes() != row_files[1].read_bytes():
        raise ValueError("prompt rows differ")
    logit_files = [Path(str(p)+".f32") for p in paths]
    if logit_files[0].stat().st_size != len(CASES)*201088*4 or \
       logit_files[0].read_bytes() != logit_files[1].read_bytes():
        raise ValueError("prompt logits differ or incomplete")
    chunk_rows = [chunks(str(p)+".chunks.tsv") for p in paths]
    stats_rows = [stats(str(p)+".stderr") for p in paths]
    if len(chunk_rows[0]) != len(chunk_rows[1]) or \
       len(stats_rows[0]) != len(chunk_rows[0]) or \
       len(stats_rows[1]) != len(chunk_rows[1]):
        raise ValueError("chunks/stats incomplete")
    for left,right,a,b in zip(*chunk_rows,*stats_rows):
        key=lambda row:(row["case"],row["chunk"],row["start"],row["count"])
        if key(left) != key(right) or \
           (a["case"],a["chunk"]) != (left["case"],left["chunk"]) or \
           (b["case"],b["chunk"]) != (left["case"],left["chunk"]):
            raise ValueError("chunk identity/order mismatch")
    if sum(s["counters"]["preload_issued"] for s in stats_rows[0]) != 0 or \
       sum(s["counters"]["preload_issued"] for s in stats_rows[1]) <= 0:
        raise ValueError("preload intervention not active")
    cases=[]
    for case in CASES:
        arm=[]
        for chunk,stat in zip(chunk_rows,stats_rows):
            selected=[(row,s) for row,s in zip(chunk,stat) if row["case"]==case]
            if not selected:
                raise ValueError("case missing")
            arm.append({"wall_s":sum(row["wall_s"] for row,_ in selected),
                        "prompt_tokens":sum(row["count"] for row,_ in selected),
                        "chunks":len(selected),
                        "misses":sum(s["counters"]["misses"] for _,s in selected),
                        "preload_issued":sum(s["counters"]["preload_issued"] for _,s in selected),
                        "preload_ready":sum(s["counters"]["resident_on_arrival"] for _,s in selected),
                        "wave_wait_s":sum(s["counters"]["wave_stall_ms"] for _,s in selected)/1000})
        if arm[0]["prompt_tokens"] != arm[1]["prompt_tokens"] or \
           arm[0]["prompt_tokens"] != {"latency-short":113,
                                     "latency-medium":496,"latency-long":1522}[case]:
            raise ValueError("frozen prompt count changed")
        reduction=1-arm[1]["wall_s"]/arm[0]["wall_s"]
        cases.append({"case":case,"control":arm[0],"candidate":arm[1],
                      "prefill_reduction_fraction":reduction,
                      "meets_25pct_screen":reduction>=0.25})
    return {"schema":"c3-prefill-candidate-screen-v1","status":"PASS_SCREEN_NUMERIC_RESOURCE",
            "control_run_id":control_id,"candidate_run_id":candidate_id,
            "final_prompt_logits_bitwise_equal":True,"cases":cases,
            "goal_25pct_both_medium_long":all(c["meets_25pct_screen"] for c in cases[1:]),
            "candidate_cgroup_peak_bytes":manifests[1]["cgroup_end"]["memory_peak"],
            "candidate_gpu_sample_peak_mib":manifests[1]["maxima"]["gpu_used_mib"],
            "source_sha256":{str(p):sha(p) for p in
                             (Path(str(paths[0])+".json"),Path(str(paths[1])+".json"),
                              *row_files,*logit_files,
                              Path(str(paths[0])+".chunks.tsv"),
                              Path(str(paths[1])+".chunks.tsv"))},
            "analyzer_sha256":sha(__file__)}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("control_run_id")
    ap.add_argument("candidate_run_id")
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    try:
        result=analyze(args.control_run_id,args.candidate_run_id)
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
        result={"schema":"c3-prefill-candidate-screen-v1","status":"FAIL_EVIDENCE",
                "reason":f"{type(exc).__name__}: {exc}"}
    with args.output.open("x") as out:
        json.dump(result,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({"status":result["status"],"goal":result.get("goal_25pct_both_medium_long"),
                      "reason":result.get("reason"),
                      "cases":[(x["case"],x["prefill_reduction_fraction"]) for x in result.get("cases",[])]}))
    return 0 if result["status"].startswith("PASS") else 1


if __name__=="__main__":
    raise SystemExit(main())
