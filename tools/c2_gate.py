#!/usr/bin/env python3
"""Fail-closed, model-free gate for normalized C2 server evidence (schema c2-run-v1)."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re


class GateError(ValueError):
    pass


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GateError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json(data):
    return json.loads(data, object_pairs_hook=no_duplicates,
                      parse_constant=lambda value: (_ for _ in ()).throw(GateError(f"nonfinite JSON: {value}")))


def keys(obj, required, where):
    if type(obj) is not dict or set(obj) != set(required):
        raise GateError(f"{where} keys: expected {sorted(required)}, got {sorted(obj) if type(obj) is dict else type(obj).__name__}")


def number(value, where, *, minimum=None, positive=False, integer=False):
    if type(value) not in ((int,) if integer else (int, float)) or not math.isfinite(value):
        raise GateError(f"{where}: finite {'integer' if integer else 'number'} required")
    if minimum is not None and value < minimum or positive and value <= 0:
        raise GateError(f"{where}: out of range")
    return value


def string(value, where):
    if type(value) is not str or not value:
        raise GateError(f"{where}: nonempty string required")
    return value


def sha(value, where):
    if not re.fullmatch(r"[0-9a-f]{64}", string(value, where)):
        raise GateError(f"{where}: lowercase SHA-256 required")


IDENTITY = ("model_id", "model_sha256", "backend_sha", "binary_sha256",
            "library_sha256", "config_sha256", "workload_sha256", "input_sha256")
REQUEST = ("id", "backend_task_id", "started_s", "ended_s", "api_prompt_tokens",
           "api_completion_tokens", "backend_prompt_tokens", "backend_completion_tokens",
           "prefill_s", "decode_s", "finish_reason")
SAMPLE = ("t_s", "pid", "cgroup_memory_bytes", "cgroup_peak_bytes", "cgroup_swap_bytes",
          "cgroup_max_events", "cgroup_oom_events", "cgroup_oom_kill_events",
          "cgroup_local_max_events", "cgroup_local_oom_events", "cgroup_local_oom_kill_events",
          "rss_bytes", "proc_swap_bytes",
          "gpu_used_mib", "gpu_temperature_c", "cpu_tctl_c", "nvme_composite_c",
          "mem_available_bytes")
LIMITS = ("memory_max_bytes", "rss_max_bytes", "gpu_max_mib", "min_mem_available_bytes",
          "cpu_max_c", "gpu_max_c", "nvme_max_c", "max_gap_s", "boundary_s",
          "min_elapsed_s", "min_active_s", "min_decode_s", "min_decode_tok_s", "min_last_half_tok_s")
OUTCOME = ("elapsed_s", "returncode", "stop_reasons", "backend_errors")
TOP = ("schema_version", "campaign_id", "run_id", "protocol_id", "identity",
       "expected_request_ids", "requests", "samples", "limits", "outcome")
PROTOCOL = ("schema_version", "campaign_id", "protocol_id", "identity",
            "expected_request_ids", "limits")


def validate(doc, frozen):
    keys(doc, TOP, "run")
    keys(frozen, PROTOCOL, "frozen protocol")
    if frozen["schema_version"] != "c2-protocol-v1":
        raise GateError("unsupported protocol schema")
    for name in ("campaign_id", "protocol_id", "identity", "expected_request_ids", "limits"):
        if doc[name] != frozen[name]:
            raise GateError(f"run differs from frozen protocol: {name}")
    if doc["schema_version"] != "c2-run-v1":
        raise GateError("unsupported schema version")
    for name in ("campaign_id", "run_id", "protocol_id"):
        string(doc[name], name)
    keys(doc["identity"], IDENTITY, "identity")
    ident = doc["identity"]
    string(ident["model_id"], "model_id")
    for name in ("model_sha256", "binary_sha256", "config_sha256", "workload_sha256"):
        sha(ident[name], name)
    if not re.fullmatch(r"[0-9a-f]{40}", string(ident["backend_sha"], "backend_sha")):
        raise GateError("backend SHA must be full")
    for name in ("library_sha256", "input_sha256"):
        if type(ident[name]) is not dict or not ident[name]:
            raise GateError(f"{name}: nonempty hash map required")
        for path, digest in ident[name].items():
            string(path, f"{name} path")
            sha(digest, f"{name} digest")
    keys(doc["limits"], LIMITS, "limits")
    limits = doc["limits"]
    for name in LIMITS:
        number(limits[name], name, minimum=0)
    if not 0 < limits["boundary_s"] <= limits["max_gap_s"]:
        raise GateError("invalid telemetry cadence policy")
    keys(doc["outcome"], OUTCOME, "outcome")
    outcome = doc["outcome"]
    elapsed = number(outcome["elapsed_s"], "elapsed_s", positive=True)
    if type(outcome["returncode"]) is not int or outcome["returncode"] != 0:
        raise GateError("backend returncode is not zero")
    for name in ("stop_reasons", "backend_errors"):
        if type(outcome[name]) is not list or outcome[name]:
            raise GateError(f"{name}: must be an empty list")

    expected = doc["expected_request_ids"]
    requests = doc["requests"]
    if type(expected) is not list or not expected or type(requests) is not list:
        raise GateError("nonempty expected request IDs and request rows required")
    if any(type(x) is not str or not x for x in expected) or len(set(expected)) != len(expected):
        raise GateError("expected request IDs invalid or duplicated")
    if len(requests) != len(expected):
        raise GateError("missing or extra request")
    backend_ids = set()
    previous_backend_id = -1
    decoded = 0
    decode_s = 0.0
    active_s = 0.0
    previous_end = 0.0
    for i, (row, request_id) in enumerate(zip(requests, expected)):
        keys(row, REQUEST, f"request {i}")
        if row["id"] != request_id:
            raise GateError("request ID/order mismatch")
        backend_id = number(row["backend_task_id"], "backend task ID", minimum=0, integer=True)
        if backend_id in backend_ids:
            raise GateError("duplicate backend task ID")
        if backend_id <= previous_backend_id:
            raise GateError("backend task IDs out of order")
        backend_ids.add(backend_id)
        previous_backend_id = backend_id
        start = number(row["started_s"], "request start", minimum=0)
        end = number(row["ended_s"], "request end", positive=True)
        if not previous_end <= start < end <= elapsed:
            raise GateError("request timestamps invalid or out of order")
        previous_end = end
        active_s += end-start
        for name in ("api_prompt_tokens", "api_completion_tokens", "backend_prompt_tokens",
                     "backend_completion_tokens"):
            number(row[name], name, minimum=0, integer=True)
        if row["api_prompt_tokens"] != row["backend_prompt_tokens"] or \
           row["api_completion_tokens"] != row["backend_completion_tokens"]:
            raise GateError("API/backend token count mismatch")
        prefill = number(row["prefill_s"], "prefill_s", positive=True)
        decode = number(row["decode_s"], "decode_s", positive=True)
        if prefill + decode > end-start + 0.05:
            raise GateError("backend timings exceed request interval")
        if row["finish_reason"] not in ("stop", "length"):
            raise GateError("missing/unknown finish reason")
        decoded += row["backend_completion_tokens"]
        decode_s += decode
    if decoded <= 0:
        raise GateError("zero decoded tokens")

    samples = doc["samples"]
    if type(samples) is not list or len(samples) < 2:
        raise GateError("telemetry missing or too short")
    previous_t = None
    pid = None
    first_events = None
    peak_memory = 0
    previous_peak = 0
    for i, sample in enumerate(samples):
        keys(sample, SAMPLE, f"sample {i}")
        t = number(sample["t_s"], "sample time", minimum=0)
        p = number(sample["pid"], "sample PID", positive=True, integer=True)
        if pid is None:
            pid = p
        elif p != pid:
            raise GateError("PID changed in telemetry")
        if previous_t is not None and not 0 < t-previous_t <= limits["max_gap_s"]:
            raise GateError("telemetry nonmonotone or gap too large")
        previous_t = t
        for name in SAMPLE[2:]:
            number(sample[name], f"sample {i} {name}", minimum=0)
        for name in ("cgroup_memory_bytes", "cgroup_peak_bytes", "rss_bytes",
                     "gpu_used_mib", "gpu_temperature_c", "cpu_tctl_c",
                     "nvme_composite_c", "mem_available_bytes"):
            number(sample[name], f"sample {i} {name}", positive=True)
        if sample["cgroup_memory_bytes"] > limits["memory_max_bytes"] or \
           sample["cgroup_peak_bytes"] > limits["memory_max_bytes"] or \
           sample["rss_bytes"] > limits["rss_max_bytes"] or \
           sample["gpu_used_mib"] > limits["gpu_max_mib"] or \
           sample["mem_available_bytes"] < limits["min_mem_available_bytes"]:
            raise GateError("memory/GPU guard violated")
        if sample["cgroup_peak_bytes"] < max(sample["cgroup_memory_bytes"], previous_peak):
            raise GateError("cgroup memory peak inconsistent or decreased")
        previous_peak = sample["cgroup_peak_bytes"]
        if sample["cgroup_swap_bytes"] or sample["proc_swap_bytes"]:
            raise GateError("swap used")
        if sample["cpu_tctl_c"] > limits["cpu_max_c"] or \
           sample["gpu_temperature_c"] > limits["gpu_max_c"] or \
           sample["nvme_composite_c"] > limits["nvme_max_c"]:
            raise GateError("thermal guard violated")
        events = tuple(sample[name] for name in
                       ("cgroup_max_events", "cgroup_oom_events", "cgroup_oom_kill_events",
                        "cgroup_local_max_events", "cgroup_local_oom_events",
                        "cgroup_local_oom_kill_events"))
        if first_events is None:
            first_events = events
        elif events != first_events:
            raise GateError("cgroup memory max/OOM event increased")
        peak_memory = max(peak_memory, sample["cgroup_peak_bytes"])
    if samples[0]["t_s"] > limits["boundary_s"] or elapsed-samples[-1]["t_s"] > limits["boundary_s"]:
        raise GateError("telemetry does not cover process boundaries")
    if samples[-1]["t_s"] > elapsed:
        raise GateError("telemetry extends beyond process")
    if elapsed < limits["min_elapsed_s"] or active_s < limits["min_active_s"] or \
       decode_s < limits["min_decode_s"]:
        raise GateError("sustained duration not met")
    rate = decoded/decode_s
    last = requests[len(requests)//2:]
    last_rate = sum(x["backend_completion_tokens"] for x in last)/sum(x["decode_s"] for x in last)
    if rate < limits["min_decode_tok_s"] or last_rate < limits["min_last_half_tok_s"]:
        raise GateError("decode throughput threshold not met")
    return {"status": "PASS", "schema_version": "c2-gate-result-v1", "run_id": doc["run_id"],
            "completed_requests": len(requests), "active_s": active_s,
            "decode_tokens": decoded, "decode_s": decode_s,
            "decode_tok_s": rate, "last_half_decode_tok_s": last_rate,
            "sample_count": len(samples), "cgroup_peak_bytes": peak_memory}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("--protocol", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    try:
        doc = strict_json(Path(args.input).read_text())
        frozen = strict_json(Path(args.protocol).read_text())
        result = validate(doc, frozen)
        result["source_sha256"] = hashlib.sha256(Path(args.input).read_bytes()).hexdigest()
        result["protocol_sha256"] = hashlib.sha256(Path(args.protocol).read_bytes()).hexdigest()
    except (GateError, ValueError, OSError) as exc:
        result = {"status": "FAIL", "schema_version": "c2-gate-result-v1",
                  "reason": f"{type(exc).__name__}: {exc}"}
    with open(args.output, "x", encoding="utf-8") as out:
        json.dump(result, out, indent=2, allow_nan=False)
        out.write("\n")
    print(json.dumps(result, allow_nan=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
