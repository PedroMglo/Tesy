#!/usr/bin/env python3
"""Compare frozen long-prompt free generations without promoting numerical parity."""

import argparse
import hashlib
import json
from pathlib import Path

from c2_gate import strict_json


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def one(path, selected):
    doc = strict_json(path.read_text())
    rows = doc["rows"]
    row = rows[2] if selected == "historical" or selected == "preload" else rows[0]
    if row["id"] != "latency-long" or row["templated_prompt_tokens"] != 1522 or \
       row["stream"]["finish_reason"] != "stop" or row["final_answer_valid"] is not True or \
       row["stream"]["usage"]["prompt_tokens"] != 1522 or \
       row["stream"]["usage"]["prompt_tokens_details"]["cached_tokens"] != 0:
        raise ValueError(f"invalid {selected} request")
    return doc, row["stream"]


def main():
    ap = argparse.ArgumentParser()
    for name in ("historical", "preload", "control1", "control2", "server", "output"):
        ap.add_argument("--" + name, type=Path, required=True)
    args = ap.parse_args()
    paths = {name: getattr(args, name) for name in
             ("historical", "preload", "control1", "control2")}
    docs, streams = {}, {}
    for name, path in paths.items():
        docs[name], streams[name] = one(path, name)
    if len({d["workload_sha256"] for d in docs.values()}) != 1 or \
       len({d["policy"]["max_tokens"] for d in docs.values()}) != 1 or \
       len({d["model_id_reported"] for d in docs.values()}) != 1:
        raise ValueError("workload/policy/model differs")
    server = strict_json(args.server.read_text())
    if server["run_id"] != "c3-d1-nopreload-long-server01" or server["stop_reason"] is not None or \
       server["returncode"] != 0 or server["maxima"]["swap_bytes"] != 0 or \
       server["cgroup_end"]["swap_current"] != 0 or \
       server["cgroup_start"]["memory_max"] != 18*2**30 or \
       server["cgroup_end"]["memory_max"] != 18*2**30 or \
       server["explicit_env"].get("LLAMA_MOE_STREAM_NO_PRELOAD") != "1":
        raise ValueError("control server failed")
    for key in ("events", "events_local"):
        if any(server["cgroup_end"][key][event] != server["cgroup_start"][key][event]
               for event in ("max", "oom", "oom_kill")):
            raise ValueError("control cgroup event")
    equal_control = streams["control1"]["reasoning_text"] == streams["control2"]["reasoning_text"]
    equal_preload = all(streams[name]["reasoning_text"] == streams["preload"]["reasoning_text"]
                        for name in ("control1", "control2"))
    differs_historical = streams["control1"]["reasoning_text"] != streams["historical"]["reasoning_text"]
    same_final = len({s["final_text"] for s in streams.values()}) == 1
    status = "HISTORICAL_VARIATION_NOT_PRELOAD_SPECIFIC" if \
        equal_control and equal_preload and differs_historical and same_final else "INCONCLUSIVE"
    report = {"schema": "c3-long-generation-diagnostic-v1", "status": status,
              "scope": "free generation text; no fixed-token logit equivalence",
              "same_control_reasoning": equal_control,
              "controls_match_preload_reasoning": equal_preload,
              "control_differs_from_historical_reasoning": differs_historical,
              "same_final_text": same_final,
              "rows": {name: {"completion_tokens": s["usage"]["completion_tokens"],
                              "first_text_s": s["first_text_chunk_s"],
                              "reasoning_sha256": digest(s["reasoning_text"]),
                              "final_sha256": digest(s["final_text"])}
                       for name, s in streams.items()},
              "source_sha256": {str(path): sha(path) for path in (*paths.values(), args.server)},
              "analyzer_sha256": sha(Path(__file__))}
    with args.output.open("x") as out:
        json.dump(report, out, indent=2, allow_nan=False)
        out.write("\n")
    print(json.dumps({"status": status, "same_control": equal_control,
                      "controls_match_preload": equal_preload,
                      "differs_historical": differs_historical}))


if __name__ == "__main__":
    main()
