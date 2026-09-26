#!/usr/bin/env python3
"""Summarize bounded CLI sustained timing without inferring per-token chunk latency."""

import argparse
import json
from pathlib import Path
import re
import statistics as stats


ROOT = Path(__file__).resolve().parents[1]


def pairs(stderr, name):
    return [(int(tokens), float(ms) / 1000) for ms, tokens in
            re.findall(r"(?m)^.*?" + name + r" time =\s*([\d.]+) ms /\s*(\d+) tokens", stderr)]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("run_id")
    a = p.parse_args()
    stem = ROOT / "results" / a.run_id
    manifest = json.loads(Path(str(stem) + ".json").read_text())
    stderr = Path(str(stem) + ".stderr").read_text(errors="replace")
    stdout = Path(str(stem) + ".stdout").read_text(errors="replace")
    samples = [json.loads(line) for line in Path(str(stem) + ".samples.jsonl").read_text().splitlines()]
    prefill = pairs(stderr, "prompt eval")
    decode = pairs(stderr, "eval")
    # The plain 'eval time' regex excludes 'prompt eval time' because the latter
    # has no whitespace immediately before eval in the full pattern? Filter below.
    decode = [(n, s) for n, s in decode if (n, s) not in prefill]
    answers = re.findall(r"\[Start thinking\](.*?)\[ Prompt:", stdout, re.S)
    requests = []
    for i, ((np, sp), (nd, sd)) in enumerate(zip(prefill, decode)):
        content = answers[i] if i < len(answers) else ""
        final = content.split("[End thinking]", 1)[1] if "[End thinking]" in content else ""
        requests.append({"request_index": i + 1, "prefill_tokens": np,
                         "prefill_s": sp, "prefill_tok_s": np / sp,
                         "decoded_tokens": nd, "decode_s": sd,
                         "decode_tok_s": nd / sd,
                         "final_visible_characters": len(final.strip()),
                         "final_token_count": None})
    windows = []
    for start in range(0, int(manifest["elapsed_s"]), 300):
        rows = [row for row in samples if start <= row["elapsed_s"] < start + 300]
        if not rows:
            continue
        def temps(key):
            vals = [row["thermal"][key] for row in rows if row.get("thermal") and key in row["thermal"]]
            return {"median": stats.median(vals), "max": max(vals)} if vals else None
        gpu = [row["gpu"]["temperature_c"] for row in rows if row.get("gpu")]
        reads = [row["proc"]["read_bytes"] for row in rows if "read_bytes" in row.get("proc", {})]
        windows.append({"start_s": start, "end_s": min(start + 300, manifest["elapsed_s"]),
                        "cpu_tctl_c": temps("cpu_tctl_c"),
                        "nvme_composite_c": temps("nvme_composite_c"),
                        "gpu_temp_c": {"median": stats.median(gpu), "max": max(gpu)} if gpu else None,
                        "read_bytes_delta_sampled": reads[-1] - reads[0] if len(reads) > 1 else None})
    total_tokens = sum(row["decoded_tokens"] for row in requests)
    total_decode_s = sum(row["decode_s"] for row in requests)
    last = requests[len(requests)//2:]
    last_tokens = sum(row["decoded_tokens"] for row in last)
    last_decode_s = sum(row["decode_s"] for row in last)
    events = manifest.get("cgroup_end", {}).get("events", {})
    initial = manifest.get("cgroup_start", {}).get("events", {})
    resource_ok = (manifest["maxima"]["swap_bytes"] == 0 and
                   all(events.get(key, 0) == initial.get(key, 0) for key in ("max", "oom", "oom_kill")))
    qualified = (len(requests) == 8 and len(prefill) == len(decode) == 8 and
                 manifest["returncode"] == 0 and manifest["stop_reason"] is None and
                 manifest["elapsed_s"] >= 900 and resource_ok and
                 total_tokens / total_decode_s >= 2 and
                 last_tokens / last_decode_s >= 2)
    report = {"run_id": a.run_id, "completed_requests": len(requests),
              "planned_requests": 8, "requests": requests,
              "total_decoded_tokens": total_tokens, "total_decode_s": total_decode_s,
              "aggregate_decode_tok_s": total_tokens / total_decode_s if total_decode_s else None,
              "last_half_decode_tok_s": last_tokens / last_decode_s if last_decode_s else None,
              "elapsed_s": manifest["elapsed_s"], "stop_reason": manifest["stop_reason"],
              "resource_ok": resource_ok, "m5_frozen_criterion_met": qualified,
              "thermal_windows": windows,
              "limitations": ["read_bytes is a process counter, not exclusive NVMe traffic",
                              "final visible token count and per-token p50/p95 are not measured by this CLI run"]}
    Path(str(stem) + "-analysis.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("completed_requests", "aggregate_decode_tok_s",
                                                  "last_half_decode_tok_s", "elapsed_s",
                                                  "stop_reason", "m5_frozen_criterion_met")}))


if __name__ == "__main__":
    main()
