#!/usr/bin/env python3
"""Approve a C3 server run only after its raw, normalized and published evidence agrees."""

import argparse
import json
from pathlib import Path

from c2_gate import GateError, keys, number, strict_json, validate
from c2_server_run import normalize
from run_bounded import sha256


ROOT = Path(__file__).resolve().parents[1]
IDENTITY = ("pid", "start_ticks", "cgroup_path", "cgroup_inode")
SAMPLE = ("elapsed_s", "pid", "process_identity", "proc", "cgroup", "gpu",
          "thermal", "mem_available_bytes", "model_fds", "collection_s")
ARTIFACTS = (".preflight.json", ".launch.json", ".json", ".normalized.json",
             ".stdout", ".stderr", ".samples.jsonl", ".gate.json")


def checked(condition, message):
    if not condition:
        raise GateError(message)


def approval(stem, protocol_path):
    stem = Path(stem)
    paths = {suffix: Path(str(stem) + suffix) for suffix in ARTIFACTS}
    published_path = Path(str(stem) + ".published.json")
    checked(all(path.is_file() for path in paths.values()) and published_path.is_file(),
            "complete raw/gate/publication files required")
    protocol = strict_json(Path(protocol_path).read_text())
    preflight, launch, raw, normalized, gate, published = (
        strict_json(paths[".preflight.json"].read_text()),
        strict_json(paths[".launch.json"].read_text()),
        strict_json(paths[".json"].read_text()),
        strict_json(paths[".normalized.json"].read_text()),
        strict_json(paths[".gate.json"].read_text()),
        strict_json(published_path.read_text()),
    )
    run_id = stem.name
    checked(preflight["run_id"] == launch["run_id"] == raw["preflight"]["run_id"] ==
            normalized["run_id"] == gate["run_id"] == published["run_id"] == run_id,
            "run ID differs across artifacts")
    checked(preflight["protocol_sha256"] == sha256(protocol_path) and
            preflight["protocol"] == protocol, "preflight protocol differs")
    checked(all(raw["preflight"].get(k) == v for k, v in preflight.items()),
            "raw preflight differs from before-launch file")
    checked(raw["preflight"].get("actually_loaded_backend_libraries_sha256") ==
            protocol["identity"]["library_sha256"], "loaded libraries differ")
    checked(raw["preflight"].get("runner_sha256") == preflight["runner_sha256"],
            "runner identity differs")
    keys(launch, ("schema_version", "run_id", "process_identity", "cgroup_start",
                  "preflight_sha256"), "launch")
    checked(launch["schema_version"] == "c3-launch-v1" and
            launch["preflight_sha256"] == sha256(paths[".preflight.json"]) and
            launch["cgroup_start"] == preflight["cgroup_start"],
            "launch baseline/preflight differs")
    identity = launch["process_identity"]
    keys(identity, IDENTITY, "launch process identity")
    number(identity["pid"], "launch pid", positive=True, integer=True)
    number(identity["start_ticks"], "launch start ticks", positive=True, integer=True)
    number(identity["cgroup_inode"], "launch cgroup inode", positive=True, integer=True)
    checked(type(identity["cgroup_path"]) is str and identity["cgroup_path"].startswith("/"),
            "launch cgroup path invalid")
    checked(raw.get("launch_identity") == identity and
            raw["preflight"].get("launch_identity") == identity,
            "raw launch identity differs")
    start = launch["cgroup_start"]
    end = raw.get("cgroup_end")
    checked(type(start) is dict and type(end) is dict and
            start.get("path") == end.get("path") == identity["cgroup_path"],
            "cgroup path differs")
    checked(start.get("memory_max") == end.get("memory_max") ==
            protocol["limits"]["memory_max_bytes"] and
            start.get("swap_max") == end.get("swap_max") == 0,
            "cgroup memory/swap limit differs")
    for group in ("events", "events_local"):
        checked(type(start.get(group)) is dict and type(end.get(group)) is dict,
                "cgroup event group missing")
        for event in ("oom", "oom_kill"):
            checked(start[group].get(event) == 0, "nonzero pre-model OOM/kill baseline")
        for event in ("max", "oom", "oom_kill"):
            checked(type(start[group].get(event)) is int and
                    end[group].get(event) == start[group][event],
                    "cgroup event changed after final sample")
    checked(end.get("swap_current") == 0 and
            type(end.get("memory_peak")) is int and
            end["memory_peak"] <= end["memory_max"], "end resource violation")
    checked(raw.get("stop_reasons") == [] and raw.get("returncode") == 0,
            "raw run did not end cleanly")

    lines = paths[".samples.jsonl"].read_text().splitlines()
    samples = [strict_json(line) for line in lines]
    checked(len(samples) == raw.get("sample_count") and len(samples) >= 2,
            "raw sample count differs")
    for sample in samples:
        keys(sample, SAMPLE, "raw sample")
        checked(sample["pid"] == identity["pid"] and
                sample["process_identity"] == identity and
                sample["cgroup"].get("path") == identity["cgroup_path"],
                "sample process/cgroup differs from launch")
        checked(sample["cgroup"].get("memory_max") == start["memory_max"] and
                sample["cgroup"].get("swap_max") == 0,
                "sample cgroup limits differ")
        for group in ("events", "events_local"):
            checked(all(sample["cgroup"][group].get(event) == start[group][event]
                        for event in ("max", "oom", "oom_kill")),
                    "sample cgroup event differs from baseline")
    checked(raw.get("source_sha256") ==
            {suffix: sha256(paths[suffix]) for suffix in
             (".launch.json", ".stdout", ".stderr", ".samples.jsonl")},
            "raw source hashes differ")
    recomputed = normalize(raw["results"], protocol, raw["preflight"]["config"],
                           samples, paths[".stderr"].read_text(errors="replace"),
                           raw["elapsed_s"], raw["returncode"], raw["stop_reasons"])
    checked(recomputed == normalized, "normalized data differs from raw evidence")
    measured = validate(normalized, protocol)
    checked(gate.get("status") == "PASS" and
            gate.get("source_sha256") == sha256(paths[".normalized.json"]) and
            gate.get("protocol_sha256") == sha256(protocol_path) and
            all(gate.get(key) == value for key, value in measured.items()),
            "gate differs from recomputed validation")
    checked(published.get("status") == "PASS" and
            published.get("end_resource_ok") is True and
            published.get("raw_stop_reasons") == [],
            "publication/end-resource check did not pass")
    checked(all(published.get("source_sha256", {}).get(
                    str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)) == sha256(path)
                for path in (*paths.values(), Path(protocol_path))),
            "publication source hashes differ")
    return {"schema_version":"c3-approval-v1", "status":"PASS", "run_id":run_id,
            "launch_identity":identity, "sample_count":len(samples),
            "decode_tok_s":measured["decode_tok_s"],
            "source_sha256":sha256(published_path)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stem", type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = approval(args.stem, args.protocol)
    except (GateError, KeyError, ValueError, OSError, TypeError) as exc:
        result = {"schema_version":"c3-approval-v1", "status":"FAIL",
                  "reason":f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, allow_nan=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
