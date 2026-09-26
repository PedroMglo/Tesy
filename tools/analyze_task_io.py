#!/usr/bin/env python3
"""Approximate process read_bytes by server request and phase from saved samples."""

import argparse
from bisect import bisect_right
import json
from pathlib import Path
import re


STAMP = re.compile(r"^(\d+)\.(\d{2})\.(\d{3})\.(\d{3}) ")
LAUNCH = re.compile(r"slot launch_slot_:.*\| task (\d+) \|")
DONE = re.compile(r"slot print_timing:.*\| task (\d+) \|\s+total time =")


def timestamp(line):
    match = STAMP.match(line)
    if not match:
        return None
    minutes, seconds, millis, micros = map(int, match.groups())
    return 60*minutes + seconds + millis/1000 + micros/1_000_000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    args = parser.parse_args()
    stem = Path("results") / args.run_id
    manifest = json.loads(stem.with_suffix(".json").read_text())
    samples = [json.loads(line) for line in Path(str(stem) + ".samples.jsonl").read_text().splitlines()]
    times = [sample["elapsed_s"] for sample in samples]
    reads = [sample["proc"]["read_bytes"] for sample in samples]
    if any(a >= b for a, b in zip(times, times[1:])) or any(a > b for a, b in zip(reads, reads[1:])):
        raise ValueError("sample times or process read_bytes are not monotone")

    starts = []
    ends = []
    for line in Path(str(stem) + ".stderr").read_text(errors="replace").splitlines():
        t = timestamp(line)
        if t is None:
            continue
        if match := LAUNCH.search(line):
            starts.append((int(match.group(1)), t))
        if match := DONE.search(line):
            ends.append((int(match.group(1)), t))
    if len(starts) != len(ends) or len(starts) != len(manifest["results"]) + 1:
        raise ValueError("expected one smoke and one matched timing pair per task")
    if any(a[0] != b[0] for a, b in zip(starts, ends)):
        raise ValueError("task IDs or order differ between launch and completion")

    def estimate(t):
        i = bisect_right(times, t)
        if i == 0:
            raise ValueError("timing boundary outside sample coverage")
        if i == len(times):
            if t - times[-1] > 1.5:
                raise ValueError("timing boundary too far beyond last sample")
            return reads[-1], t - times[-1]  # lower sampled bound, no invented extrapolation
        lo, hi = i - 1, i
        frac = (t - times[lo]) / (times[hi] - times[lo])
        value = reads[lo] + frac * (reads[hi] - reads[lo])
        return round(value), times[hi] - times[lo]

    rows = []
    for item, (_, start), (_, end) in zip(manifest["results"], starts[1:], ends[1:]):
        timing = item["timings"]
        prompt_end = end - timing["predicted_ms"] / 1000
        if not start < prompt_end < end or abs((end - start) - item["elapsed_s"]) > 0.1:
            raise ValueError(f"backend/API timing mismatch for {item['task_id']}")
        r0, g0 = estimate(start)
        r1, g1 = estimate(prompt_end)
        r2, g2 = estimate(end)
        interval_samples = [sample for sample in samples if start <= sample["elapsed_s"] <= end]
        rows.append({
            "task_id": item["task_id"], "start_s": start, "prompt_end_s": prompt_end, "end_s": end,
            "prompt_tokens": item["usage"]["prompt_tokens"],
            "completion_tokens": item["usage"]["completion_tokens"],
            "process_read_bytes_prefill_est": r1-r0,
            "process_read_bytes_decode_est": r2-r1,
            "process_read_bytes_request_est": r2-r0,
            "process_read_bytes_per_completion_token_decode_est": (r2-r1)/item["usage"]["completion_tokens"],
            "max_boundary_sample_spacing_s": max(g0, g1, g2),
            "direct_fd_samples": sum((sample.get("model_fds") or {}).get("direct", 0) > 0 for sample in interval_samples),
            "buffered_fd_samples": sum((sample.get("model_fds") or {}).get("buffered", 0) > 0 for sample in interval_samples),
        })
    out = {
        "run_id": args.run_id,
        "source_manifest": str(stem) + ".json",
        "source_stderr": str(stem) + ".stderr",
        "source_samples": str(stem) + ".samples.jsonl",
        "evidence_class": "post-hoc approximate process-counter phase attribution; linear interpolation between one-second samples",
        "rows": rows,
        "total_est": {
            "prefill_read_bytes": sum(row["process_read_bytes_prefill_est"] for row in rows),
            "decode_read_bytes": sum(row["process_read_bytes_decode_est"] for row in rows),
            "completion_tokens": sum(row["completion_tokens"] for row in rows),
            "decode_read_bytes_per_completion_token": sum(row["process_read_bytes_decode_est"] for row in rows) / sum(row["completion_tokens"] for row in rows),
        },
        "limitations": [
            "read_bytes is process-attributed block-read accounting, not exclusive physical NVMe traffic",
            "boundaries are reconstructed from server logs and one-second samples; reads may be bursty within a sample interval",
            "a final boundary up to 1.5 s after the last sample uses the last observed counter without extrapolation",
            "no per-layer, GPU/host tier, H2D, eviction or overlap attribution",
        ],
    }
    out_path = Path(str(stem) + "-io-analysis.json")
    with out_path.open("x") as target:
        target.write(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out["total_est"]))


if __name__ == "__main__":
    main()
