#!/usr/bin/env python3
"""Summarize two-turn 120B slot-capacity runs without publishing raw output."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics

from c2_gate import strict_json


PROMPT = re.compile(r"\|\s+prompt eval time =\s+([0-9.]+) ms /\s+(\d+) tokens")
DECODE = re.compile(r"\|\s+eval time =\s+([0-9.]+) ms /\s+(\d+) tokens")
RESPONSE = re.compile(r"\[Start thinking\].*?(?=\[ Prompt:)", re.S)


def row(run_id):
    stem = Path("results") / run_id
    manifest = strict_json(stem.with_suffix(".json").read_text())
    stderr = Path(str(stem) + ".stderr").read_text(errors="replace")
    stdout = Path(str(stem) + ".stdout").read_text(errors="replace")
    samples = [strict_json(line) for line in Path(str(stem) + ".samples.jsonl").read_text().splitlines()]
    telemetry_ok = (len(samples) >= 2 and samples[0]["elapsed_s"] <= 2.5 and
                    0 <= manifest["elapsed_s"] - samples[-1]["elapsed_s"] <= 2.5 and
                    all(0 < b["elapsed_s"] - a["elapsed_s"] <= 3
                        for a, b in zip(samples, samples[1:])) and
                    all(s.get("proc") and s.get("gpu") and s.get("thermal") and s.get("cgroup") and
                        s.get("mem_available_bytes") is not None for s in samples))
    prompts = [(int(n), float(ms)/1000) for ms, n in PROMPT.findall(stderr)]
    decodes = [(int(n), float(ms)/1000) for ms, n in DECODE.findall(stderr)]
    responses = RESPONSE.findall(stdout)
    if len(prompts) != 2 or len(decodes) != 2 or len(responses) != 2:
        raise ValueError(f"expected two prompt/decode/output segments: {run_id}")
    events0 = manifest["cgroup_start"]["events"]
    events1 = manifest["cgroup_end"]["events"]
    return {
        "run_id": run_id, "cache_slots": int(re.search(r"stream(\d+)-direct", manifest["variant"]).group(1)),
        "backend_sha": manifest["backend_sha"], "binary_sha256": manifest["binary_sha256"],
        "prefill": prompts, "decode": decodes,
        "decode_tok_s": sum(n for n, _ in decodes) / sum(s for _, s in decodes),
        "per_request_decode_tok_s": [n/s for n, s in decodes],
        "elapsed_s": manifest["elapsed_s"],
        "process_read_bytes_sampled": manifest["last_sample"]["proc"]["read_bytes"],
        "cgroup_peak_bytes": manifest["maxima"]["cgroup_memory_bytes"],
        "gpu_peak_mib": manifest["maxima"]["gpu_used_mib"],
        "swap_peak_bytes": manifest["maxima"]["swap_bytes"],
        "cgroup_max_event_delta": events1["max"] - events0["max"],
        "oom_event_delta": events1["oom"] - events0["oom"],
        "returncode": manifest["returncode"], "stop_reason": manifest["stop_reason"],
        "legacy_telemetry_coverage_ok": telemetry_ok,
        "response_hashes": [hashlib.sha256(s.encode()).hexdigest() for s in responses],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_ids", nargs="+")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows = [row(run_id) for run_id in args.run_ids]
    by_slots = {slots: [r for r in rows if r["cache_slots"] == slots]
                for slots in sorted({r["cache_slots"] for r in rows})}
    summary = {
        str(slots): {
            "n_runs": len(group),
            "mean_decode_tok_s": statistics.mean(r["decode_tok_s"] for r in group),
            "mean_elapsed_s": statistics.mean(r["elapsed_s"] for r in group),
            "mean_process_read_bytes_sampled": statistics.mean(r["process_read_bytes_sampled"] for r in group),
        } for slots, group in by_slots.items()
    }
    report = {
        "run_order": args.run_ids, "rows": rows, "summary": summary,
        "all_same_response_hashes": len({tuple(r["response_hashes"]) for r in rows}) == 1,
        "all_resource_and_exit_ok": all(r["returncode"] == 0 and r["stop_reason"] is None and
                                    r["legacy_telemetry_coverage_ok"] and
                                    r["swap_peak_bytes"] == r["cgroup_max_event_delta"] ==
                                    r["oom_event_delta"] == 0 for r in rows),
        "limits": "read_bytes is sampled process accounting, not exclusive physical NVMe bytes; response hashes remove CLI timing banners but do not establish full numeric parity",
    }
    with Path(args.output).open("x") as out:
        out.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"summary": summary, "same_responses": report["all_same_response_hashes"],
                      "resource_ok": report["all_resource_and_exit_ok"]}))


if __name__ == "__main__":
    main()
