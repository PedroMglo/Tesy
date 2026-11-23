#!/usr/bin/env python3
"""Fail-closed compact summary of the frozen C3 preload latency probe."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from c2_gate import strict_json
from c2_server_run import backend_timings


EXPECTED = (("latency-short", 113), ("latency-medium", 496), ("latency-long", 1522))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(condition, message):
    if not condition:
        raise ValueError(message)


def finite_nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", type=Path, required=True)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    client, server, baseline, protocol = (strict_json(path.read_text()) for path in
                                         (args.client, args.server, args.baseline, args.protocol))
    check(client["schema_version"] == baseline["schema_version"] == "c2-latency-client-v1", "client schema")
    check(client["workload_sha256"] == baseline["workload_sha256"], "workload differs")
    check(client["policy"] == baseline["policy"], "request policy differs")
    check(client["model_id_reported"] == baseline["model_id_reported"] == server["model_path"], "model path differs")
    check([r["id"] for r in client["rows"]] == [r["id"] for r in baseline["rows"]] ==
          [item[0] for item in EXPECTED], "request IDs/order differ")
    check(server["run_id"] == args.server.stem and server["variant"] == "c3-target32-next-wave-preload", "server run identity")
    identity = protocol["identity"]
    check(server["artifact_identity"]["sha256_previously_verified"] == identity["model_sha256"] and
          server["backend_sha"] == identity["backend_sha"] and
          server["binary_sha256"] == identity["binary_sha256"] and
          server["backend_libraries_sha256"] == identity["library_sha256"], "server artifact/backend identity")
    check(server["returncode"] == 0 and server["stop_reason"] is None and
          server["cgroup_limit_enforced"] is True and server["explicit_env"] == {}, "server stop/envelope")
    start, end = server["cgroup_start"], server["cgroup_end"]
    check(start["path"] == end["path"] and start["memory_max"] == end["memory_max"] == 18*2**30 and
          start["swap_max"] == end["swap_max"] == 0 and end["swap_current"] == 0, "cgroup limit/swap")
    for key in ("events", "events_local"):
        check(all(end[key][name] == start[key][name] for name in ("max", "oom", "oom_kill")), "cgroup event delta")
    m = server["maxima"]
    check(m["cgroup_peak_bytes"] < 18*2**30 and m["rss_bytes"] <= 17*2**30 and
          m["swap_bytes"] == 0 and m["gpu_used_mib"] <= 7000 and
          m["cpu_tctl_c"] <= 95 and m["gpu_temperature_c"] <= 80 and
          m["nvme_composite_c"] <= 70, "resource guard")
    samples_path = args.server.with_suffix(".samples.jsonl")
    stderr_path = args.server.with_suffix(".stderr")
    check(sha(samples_path) == server["output_sha256"][".samples.jsonl"] and
          sha(stderr_path) == server["output_sha256"][".stderr"], "raw output hash")
    samples = [strict_json(line) for line in samples_path.read_text().splitlines()]
    check(len(samples) > 2 and samples[0]["elapsed_s"] <= 2 and
          server["elapsed_s"] - samples[-1]["elapsed_s"] <= 2 and
          all(0 < b["elapsed_s"]-a["elapsed_s"] <= 3 for a, b in zip(samples, samples[1:])) and
          len({s["pid"] for s in samples}) == 1, "telemetry coverage")
    timers = backend_timings(stderr_path.read_text(errors="replace"))
    check(len(timers) == 3, "backend timer count")
    used = set()
    rows = []
    for (name, expected_tokens), new, old in zip(EXPECTED, client["rows"], baseline["rows"]):
        usage = new["stream"]["usage"]
        check(new["templated_prompt_tokens"] == old["templated_prompt_tokens"] == expected_tokens and
              usage["prompt_tokens"] == expected_tokens and
              usage["total_tokens"] == expected_tokens + usage["completion_tokens"] and
              usage["prompt_tokens_details"]["cached_tokens"] == 0 and
              expected_tokens + 512 <= 4096 and new["final_answer_valid"] is True and
              new["stream"]["finish_reason"] == "stop", "request count or final answer")
        s = new["stream"]
        check(all(finite_nonnegative(s[key]) for key in
                  ("first_text_chunk_s", "first_final_chunk_s", "elapsed_s")) and
              s["first_text_chunk_s"] <= s["first_final_chunk_s"] <= s["elapsed_s"], "latency order")
        matches = [task for task, pair in timers.items()
                   if pair["prompt eval"][0] == expected_tokens and
                   pair["eval"][0] == usage["completion_tokens"]]
        check(len(matches) == 1 and matches[0] not in used, "backend timer match")
        task = matches[0]
        used.add(task)
        rows.append({"id": name, "prompt_tokens": expected_tokens,
                     "completion_tokens": usage["completion_tokens"],
                     "prefill_s": timers[task]["prompt eval"][1]/1000,
                     "decode_s": timers[task]["eval"][1]/1000,
                     "first_text_s": s["first_text_chunk_s"],
                     "first_final_s": s["first_final_chunk_s"],
                     "completed_s": s["elapsed_s"],
                     "baseline_first_text_s": old["stream"]["first_text_chunk_s"],
                     "baseline_first_final_s": old["stream"]["first_final_chunk_s"],
                     "baseline_completed_s": old["stream"]["elapsed_s"],
                     "reasoning_equal_to_historical": s["reasoning_text"] == old["stream"]["reasoning_text"],
                     "final_equal_to_historical": s["final_text"] == old["stream"]["final_text"],
                     "answer_valid": True})
    check(len(used) == 3, "unpaired backend timer")
    status = "MEASURED_WITH_OUTPUT_DIVERGENCE" if any(not r["reasoning_equal_to_historical"] or
                                                     not r["final_equal_to_historical"] for r in rows) else "MEASURED_MATCHING_TEXT"
    report = {"schema": "c3-preload-latency-summary-v1", "status": status,
              "run_id": server["run_id"], "rows": rows,
              "resource": {"sample_count": len(samples), "maxima": m,
                           "zero_swap_oom_max_events": True},
              "limitations": ["historical comparator, not paired causal A/B",
                              "SSE chunks are not token intervals",
                              "reasoning divergence blocks broad preload promotion"],
              "source_sha256": {str(path): sha(path) for path in
                                (args.client, args.server, args.baseline, args.protocol, samples_path, stderr_path)},
              "analyzer_sha256": sha(Path(__file__))}
    with args.output.open("x") as out:
        json.dump(report, out, indent=2, allow_nan=False)
        out.write("\n")
    print(json.dumps({"status": status, "rows": [(r["id"], r["first_text_s"]) for r in rows]}))


if __name__ == "__main__":
    main()
