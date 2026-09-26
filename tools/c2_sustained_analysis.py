#!/usr/bin/env python3
"""Descriptive C2 sustained report; never upgrades a failed frozen gate."""

import argparse
import json
from pathlib import Path
import statistics

from c2_gate import GateError, strict_json
from run_bounded import sha256


ROOT = Path(__file__).resolve().parents[1]


def analyze(run_id):
    stem = ROOT/"results"/run_id
    paths = {name:Path(str(stem)+name) for name in
             (".json",".normalized.json",".gate.json",".samples.jsonl",".stderr")}
    raw = strict_json(paths[".json"].read_text())
    gate = strict_json(paths[".gate.json"].read_text()) if paths[".gate.json"].exists() else None
    samples = [strict_json(line) for line in paths[".samples.jsonl"].read_text().splitlines()]
    normalized = strict_json(paths[".normalized.json"].read_text()) if paths[".normalized.json"].exists() else None
    if raw["preflight"]["run_id"] != run_id or not samples:
        raise GateError("run identity or samples missing")
    source_hash = {name:sha256(path) for name,path in paths.items() if path.exists()}
    if any(raw["source_sha256"].get(name) != source_hash[name]
           for name in (".stderr",".samples.jsonl")):
        raise GateError("raw file hash differs from final runner manifest")
    if gate and gate["status"] == "PASS":
        if normalized is None or gate["source_sha256"] != source_hash[".normalized.json"]:
            raise GateError("PASS gate source mismatch")
    requests = []
    if normalized is not None:
        expected = normalized["expected_request_ids"]
        rows = normalized["requests"]
        raw_rows = raw["results"]
        if len(rows) != len(raw_rows) or [x["id"] for x in rows] != [x["id"] for x in raw_rows]:
            raise GateError("normalized/raw request identity mismatch")
        for i,row in enumerate(rows):
            item = raw_rows[i]
            requests.append({"id":row["id"],"source_task_id":item["source_task_id"],
                             "block":1+i//10 if len(expected)==20 else None,
                             "started_s":row["started_s"],"ended_s":row["ended_s"],
                             "wall_s":row["ended_s"]-row["started_s"],
                             "prompt_tokens":row["backend_prompt_tokens"],
                             "completion_tokens":row["backend_completion_tokens"],
                             "prefill_s":row["prefill_s"],"decode_s":row["decode_s"],
                             "decode_tok_s":row["backend_completion_tokens"]/row["decode_s"],
                             "finish_reason":row["finish_reason"],
                             "final_characters":len((item["message"] or {}).get("content") or ""),
                             "reasoning_characters":len((item["message"] or {}).get("reasoning_content") or "")})
    def summary(items):
        tokens = sum(x["completion_tokens"] for x in items)
        decode = sum(x["decode_s"] for x in items)
        return {"requests":len(items),"completion_tokens":tokens,"decode_s":decode,
                "decode_tok_s":tokens/decode if decode else None,
                "prefill_s":sum(x["prefill_s"] for x in items),
                "active_request_s":sum(x["wall_s"] for x in items),
                "min_request_decode_tok_s":min((x["decode_tok_s"] for x in items),default=None),
                "truncated_requests":sum(x["finish_reason"]=="length" for x in items)}
    windows = []
    for start in range(0,int(raw["elapsed_s"])+1,300):
        group = [x for x in samples if start <= x["elapsed_s"] < start+300]
        if not group: continue
        values = lambda key: [x["thermal"][key] for x in group if x.get("thermal") and key in x["thermal"]]
        gpu = [x["gpu"]["temperature_c"] for x in group if x.get("gpu")]
        power = [x["gpu"]["power_w"] for x in group if x.get("gpu") and "power_w" in x["gpu"]]
        reads = [x["proc"]["read_bytes"] for x in group if x.get("proc") and "read_bytes" in x["proc"]]
        cpu = values("cpu_tctl_c"); nvme = values("nvme_composite_c")
        windows.append({"start_s":start,"end_s":min(start+300,raw["elapsed_s"]),
                        "sample_count":len(group),
                        "cpu_tctl_c_median_max":[statistics.median(cpu),max(cpu)] if cpu else None,
                        "gpu_c_median_max":[statistics.median(gpu),max(gpu)] if gpu else None,
                        "gpu_power_w_median_max":[statistics.median(power),max(power)] if power else None,
                        "nvme_c_median_max":[statistics.median(nvme),max(nvme)] if nvme else None,
                        "process_read_bytes_delta_sampled":reads[-1]-reads[0] if len(reads)>1 else None})
    cg_start = raw["preflight"]["cgroup_start"]
    cg_end = raw["cgroup_end"]
    events = {kind:{key:cg_end[source][key]-cg_start[source][key]
                    for key in ("max","oom","oom_kill")}
              for kind,source in (("hierarchical","events"),("local","events_local"))}
    end_resource_ok = (cg_end["swap_current"] == 0 and
                       cg_end["memory_peak"] <= cg_end["memory_max"] and
                       all(value == 0 for group in events.values() for value in group.values()))
    whole = summary(requests)
    return {"schema_version":"c2-sustained-analysis-v1","run_id":run_id,
            "gate_status":gate["status"] if gate else "NOT_RUN",
            "combined_status":"PASS" if gate and gate["status"]=="PASS" and end_resource_ok else "FAIL",
            "end_resource_ok":end_resource_ok,
            "gate_reason":gate.get("reason") if gate else None,
            "source_sha256":source_hash,"expected_request_ids":raw["preflight"]["config"]["task_ids"],
            "completed_request_count":len(raw["results"]),
            "process_elapsed_s":raw["elapsed_s"],
            "load_to_ready_s":raw["preflight"].get("ready_elapsed_s"),
            "active_request_s":whole["active_request_s"],
            "non_request_process_s":raw["elapsed_s"]-whole["active_request_s"],
            "whole":whole,"first_ten":summary(requests[:10]),"last_ten":summary(requests[10:20]),
            "five_request_windows":[summary(requests[i:i+5]) for i in range(0,len(requests),5)],
            "requests":requests,"thermal_and_io_windows":windows,
            "resource":{"cgroup_memory_peak_bytes":max((x["cgroup"]["memory_peak"] for x in samples if x.get("cgroup")),default=None),
                        "rss_hwm_bytes":max((x["proc"].get("VmHWM",0) for x in samples),default=None),
                        "gpu_used_mib_max":max((x["gpu"]["used_mib"] for x in samples if x.get("gpu")),default=None),
                        "cgroup_swap_bytes_max":max((x["cgroup"]["swap_current"] for x in samples if x.get("cgroup")),default=None),
                        "events_delta":events},
            "limitations":["backend decode time excludes prefill and server idle, but includes waits in decode",
                           "process read_bytes is not exclusive physical NVMe traffic",
                           "one backend timer per request; per-token p50/p95 NOT_MEASURED",
                           "numeric production-placement parity remains blocked by C2-B references"]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("run_id")
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    result=analyze(a.run_id)
    with open(a.output,"x") as out:
        json.dump(result,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({k:result[k] for k in ("run_id","gate_status","completed_request_count","process_elapsed_s","whole")}))


if __name__ == "__main__":
    main()
