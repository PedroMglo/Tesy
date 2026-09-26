#!/usr/bin/env python3
"""Pair server per-request timing with frozen task results and M5 secondary gate."""

import argparse
import json
from pathlib import Path
import statistics as stats

from analyze_sustained import pairs


ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run_id")
    a = p.parse_args()
    stem = ROOT / "results" / a.run_id
    manifest = json.loads(Path(str(stem) + ".json").read_text())
    stderr = Path(str(stem) + ".stderr").read_text(errors="replace")
    samples = [json.loads(line) for line in Path(str(stem) + ".samples.jsonl").read_text().splitlines()]
    prefills = pairs(stderr, "prompt eval")
    decodes = pairs(stderr, "eval")
    # First logged response is the separate first-text smoke, then the fixed tasks.
    rows = []
    for item, prefill, decode in zip(manifest["results"], prefills[1:], decodes[1:]):
        np, sp = prefill
        nd, sd = decode
        rows.append({"task_id": item["task_id"], "prefill_tokens_backend": np,
                     "prefill_s_backend": sp, "prefill_tok_s": np / sp,
                     "decode_tokens_backend": nd, "decode_s_backend": sd,
                     "decode_tok_s_backend": nd / sd,
                     "completion_tokens_api": item["usage"]["completion_tokens"] if item["usage"] else None,
                     "request_elapsed_s": item["elapsed_s"],
                     "finish_reason": item["finish_reason"],
                     "final_content_characters": len((item["message"].get("content") or "").strip())})
    windows = []
    for start in range(0, int(manifest["elapsed_s"]), 300):
        group = [x for x in samples if start <= x["elapsed_s"] < start + 300]
        if not group:
            continue
        def values(field, key):
            vals = [x[field][key] for x in group if x.get(field) and key in x[field]]
            return {"median": stats.median(vals), "max": max(vals)} if vals else None
        reads = [x["proc"]["read_bytes"] for x in group if "read_bytes" in x.get("proc", {})]
        windows.append({"start_s": start,
                        "end_s": min(start + 300, manifest["elapsed_s"]),
                        "cpu_tctl_c": values("thermal", "cpu_tctl_c"),
                        "nvme_composite_c": values("thermal", "nvme_composite_c"),
                        "gpu_temp_c": values("gpu", "temperature_c"),
                        "process_read_bytes_delta_sampled": reads[-1] - reads[0] if len(reads) > 1 else None})
    totals = {"decode_tokens": sum(x["decode_tokens_backend"] for x in rows),
              "decode_s": sum(x["decode_s_backend"] for x in rows)}
    last = rows[-5:]
    last_totals = {"decode_tokens": sum(x["decode_tokens_backend"] for x in last),
                   "decode_s": sum(x["decode_s_backend"] for x in last)}
    complete = (len(manifest["results"]) == 10 and len(prefills) == len(decodes) == 11 and
                len(rows) == 10 and not manifest["stop_reasons"])
    counts_agree = complete and all(x["decode_tokens_backend"] == x["completion_tokens_api"] for x in rows)
    before = manifest["cgroup_start"]["events"]
    after = manifest["cgroup_end"]["events"]
    resource_ok = (manifest["maxima"]["swap_bytes"] == 0 and
                   all(after.get(k, 0) == before.get(k, 0) for k in ("max", "oom", "oom_kill")))
    overall_rate = totals["decode_tokens"] / totals["decode_s"] if totals["decode_s"] else None
    last_rate = last_totals["decode_tokens"] / last_totals["decode_s"] if last_totals["decode_s"] else None
    m5 = (manifest["model"] == "target120b" and complete and resource_ok and
          manifest["elapsed_s"] >= 900 and overall_rate >= 2 and last_rate >= 2)
    report = {"run_id": a.run_id, "completed_task_requests": len(rows),
              "complete_timing_coverage": complete, "backend_api_token_counts_agree": counts_agree,
              "rows": rows, "total": totals, "aggregate_decode_tok_s": overall_rate,
              "last_five_decode_tok_s": last_rate, "sum_request_elapsed_s": sum(x["request_elapsed_s"] for x in rows),
              "whole_process_elapsed_s": manifest["elapsed_s"],
              "first_text_smoke": manifest.get("first_text_smoke"),
              "resource_ok": resource_ok, "m5_secondary_frozen_criterion_met": m5,
              "thermal_windows": windows,
              "limitations": ["first streamed text is client chunk arrival, not a per-token interval",
                              "process read_bytes is not exclusive physical NVMe traffic",
                              "backend decode timings exclude server request overhead but whole elapsed includes it"]}
    Path(str(stem) + "-analysis.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("completed_task_requests", "aggregate_decode_tok_s",
                                                  "last_five_decode_tok_s", "whole_process_elapsed_s",
                                                  "m5_secondary_frozen_criterion_met")}))


if __name__ == "__main__":
    main()
