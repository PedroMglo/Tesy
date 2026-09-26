#!/usr/bin/env python3
"""Frozen C2 localhost server run; reuse run_task_server and run_bounded primitives."""

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import threading
import time

from c2_gate import GateError, strict_json
from run_bounded import (backend_library_hashes, cgroup_state, gpu_state,
                         mem_available, model_fd_state, proc_status, sha256,
                         thermal_state)
from run_task_server import fetch, stop_own_server


ROOT = Path(__file__).resolve().parents[1]
MODEL = {
    "target120b": ("streaming", "/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf",
                   "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d", 8),
    "stock20b": ("stock", "/home/pmglo/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf",
                 "52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4", 14),
}
HISTORIC = ROOT / "workloads/task_eval.jsonl"
C2_TASKS = ROOT / "workloads/c2_tasks.json"
SMOKE = ROOT / "workloads/c2_smoke.json"
CORE_IDS = ("c2-eval-code-01", "c2-eval-code-02", "c2-eval-sql-01", "c2-eval-sql-02",
            "c2-eval-quant-01", "c2-eval-plan-01", "c2-eval-spec-01", "c2-eval-spec-02")
TIMING = re.compile(r"slot print_timing: id\s+\d+ \| task (\d+) \|\s*"
                    r"(prompt eval|eval) time =\s*([\d.]+) ms /\s*(\d+) tokens")


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(json_bytes(value)).hexdigest()


def tasks_for(suite):
    if suite == "smoke1":
        tasks = strict_json(SMOKE.read_text())["tasks"]
        if len(tasks) != 1 or tasks[0]["id"] != "c2-smoke-arithmetic":
            raise GateError("smoke task changed")
        return [(tasks[0]["id"],tasks[0])], SMOKE
    if suite == "historic20":
        tasks = [json.loads(line) for line in HISTORIC.read_text().splitlines()]
        tasks = [x for x in tasks if x["split"] == "eval"]
        if len(tasks) != 10 or len({x["id"] for x in tasks}) != 10:
            raise GateError("historic eval suite is not ten unique tasks")
        return [(f"block{block}-{x['id']}", x) for block in (1, 2) for x in tasks], HISTORIC
    if suite == "c2core8":
        tasks = strict_json(C2_TASKS.read_text())["tasks"]
        found = {x["id"]:x for x in tasks}
        if any(x not in found or found[x]["split"] != "eval" for x in CORE_IDS):
            raise GateError("frozen core8 tasks unavailable")
        return [(x,found[x]) for x in CORE_IDS], C2_TASKS
    raise GateError("unknown suite")


def configuration(args):
    backend_name, model_name, model_hash, default_ngl = MODEL[args.model]
    backend = ROOT / "backends" / backend_name
    binary = backend / "build-gcc15/bin/llama-server"
    model = Path(model_name)
    if not binary.is_file() or not model.is_file():
        raise GateError("model or server binary unavailable")
    ngl = default_ngl if args.model == "stock20b" else args.ngl
    command = [str(binary), "-m", str(model), "--host", "127.0.0.1", "--port", "18367",
               "-ngl", str(ngl), "-c", "4096", "-np", "1", "-b", "256", "-ub", str(args.ubatch),
               "-t", "8", "-tb", "8", "--no-warmup", "--no-cache-prompt", "-lv", "3"]
    if args.model == "stock20b":
        command += ["--load-mode", "dio", "--lazy-mode", "off", "--reasoning-effort", "medium"]
    else:
        command += ["--no-repack", "--no-op-offload", "--direct-io", "--moe-stream-cache",
                    f"{args.slots}s", "--moe-stream-io-threads", "4", "--moe-stream-direct",
                    "--chat-template-kwargs", '{"reasoning_effort":"medium"}']
    explicit_env = {"LLAMA_MOE_STREAM_NO_PRELOAD":"1"} if args.model == "target120b" else {}
    task_rows, workload = tasks_for(args.suite)
    max_tokens = 64 if args.suite == "smoke1" else 512 if args.suite == "historic20" else 2048
    request_timeout = 180 if args.suite == "smoke1" else 360 if args.suite == "historic20" else 1200
    policy = {"temperature":0,"seed":42,"max_tokens":max_tokens,"reasoning_effort":"medium",
              "attempts":1,"prompt_cache":False,"per_request_timeout_s":request_timeout}
    config = {"server_command":command,"explicit_env":explicit_env,"request_policy":policy,
              "suite":args.suite,"task_ids":[x[0] for x in task_rows]}
    if args.suite == "c2core8":
        config["total_timeout_s"] = 7200
    libs = backend_library_hashes(str(binary), backend)
    if not libs:
        raise GateError("backend shared libraries unavailable")
    identity = {"model_id":args.model,"model_sha256":model_hash,
                "backend_sha":subprocess.check_output(["git","-C",str(backend),"rev-parse","HEAD"],text=True).strip(),
                "binary_sha256":sha256(binary),"library_sha256":libs,
                "config_sha256":digest(config),"workload_sha256":sha256(workload),
                "input_sha256":{str(workload.relative_to(ROOT)):sha256(workload)}}
    limits = {"memory_max_bytes":18*2**30,"rss_max_bytes":17*2**30,
              "gpu_max_mib":7000,"min_mem_available_bytes":6*2**30,
              "cpu_max_c":95,"gpu_max_c":80,"nvme_max_c":70,
              "max_gap_s":3,"boundary_s":2,
              "min_elapsed_s":900 if args.suite == "historic20" else 0,
              "min_active_s":900 if args.suite == "historic20" else 0,
              "min_decode_s":600 if args.suite == "historic20" else 0,
              "min_decode_tok_s":2 if args.suite == "historic20" else 0,
              "min_last_half_tok_s":2 if args.suite == "historic20" else 0}
    protocol = {"schema_version":"c2-protocol-v1","campaign_id":"tesy-c2-20260926",
                "protocol_id":args.protocol_id,"identity":identity,
                "expected_request_ids":config["task_ids"],"limits":limits}
    return protocol, config, task_rows, model


def backend_timings(stderr):
    by_id = {}
    for match in TIMING.finditer(stderr):
        task_id, phase, ms, tokens = match.groups()
        task_id = int(task_id)
        record = by_id.setdefault(task_id, {})
        if phase in record:
            raise GateError(f"duplicate backend {phase} timer for task {task_id}")
        record[phase] = (int(tokens), float(ms))
    if any(set(x) != {"prompt eval", "eval"} for x in by_id.values()):
        raise GateError("backend timer pair incomplete")
    return by_id


def normalize(raw, protocol, config, samples, stderr, elapsed, returncode, reasons):
    parsed = backend_timings(stderr)
    backend_errors = [line[:1000] for line in stderr.splitlines()
                      if re.search(r"(?i)(CUDA error|\b(?:error|failed|abort|exception)\b|\sE\s)", line)]
    if len(parsed) != len(raw):
        raise GateError(f"backend timer count {len(parsed)} != request count {len(raw)}")
    used = set()
    requests = []
    for item in raw:
        usage = item.get("usage")
        timing = item.get("timings")
        if type(usage) is not dict or type(timing) is not dict:
            raise GateError("API usage or timings missing")
        if timing.get("cache_n") != 0 or \
           usage.get("prompt_tokens_details",{}).get("cached_tokens") != 0:
            raise GateError("prefix cache reuse differs from frozen protocol")
        if type(usage.get("prompt_tokens")) is not int or usage["prompt_tokens"] <= 0 or \
           type(usage.get("completion_tokens")) is not int or \
           not 0 < usage["completion_tokens"] <= config["request_policy"]["max_tokens"]:
            raise GateError("API token count missing or outside frozen request cap")
        if usage.get("total_tokens") != usage["prompt_tokens"]+usage["completion_tokens"]:
            raise GateError("API total token count inconsistent")
        if config["suite"] == "c2core8" and \
           usage["prompt_tokens"]+config["request_policy"]["max_tokens"] > 4096:
            raise GateError("templated prompt did not leave the frozen output reserve")
        matches = [task_id for task_id, pair in parsed.items() if
                   pair["prompt eval"][0] == usage.get("prompt_tokens") and
                   pair["eval"][0] == usage.get("completion_tokens") and
                   abs(pair["prompt eval"][1]-timing.get("prompt_ms",float("inf"))) <= 0.01 and
                   abs(pair["eval"][1]-timing.get("predicted_ms",float("inf"))) <= 0.01]
        if len(matches) != 1 or matches[0] in used:
            raise GateError(f"ambiguous/unmatched backend timer for {item['id']}: {matches}")
        task_id = matches[0]
        used.add(task_id)
        requests.append({"id":item["id"],"backend_task_id":task_id,
                         "started_s":item["started_s"],"ended_s":item["ended_s"],
                         "api_prompt_tokens":usage["prompt_tokens"],
                         "api_completion_tokens":usage["completion_tokens"],
                         "backend_prompt_tokens":parsed[task_id]["prompt eval"][0],
                         "backend_completion_tokens":parsed[task_id]["eval"][0],
                         "prefill_s":parsed[task_id]["prompt eval"][1]/1000,
                         "decode_s":parsed[task_id]["eval"][1]/1000,
                         "finish_reason":item["finish_reason"]})
    if len(used) != len(parsed):
        raise GateError("unpaired backend timer")
    normalized = []
    for sample in samples:
        cg, ps, gpu, th = (sample[k] for k in ("cgroup","proc","gpu","thermal"))
        if not cg or not ps or not gpu or not th:
            raise GateError("missing required telemetry")
        normalized.append({"t_s":sample["elapsed_s"],"pid":sample["pid"],
                           "cgroup_memory_bytes":cg["memory_current"],
                           "cgroup_peak_bytes":cg["memory_peak"],
                           "cgroup_swap_bytes":cg["swap_current"],
                           "cgroup_max_events":cg["events"]["max"],
                           "cgroup_oom_events":cg["events"]["oom"],
                           "cgroup_oom_kill_events":cg["events"]["oom_kill"],
                           "cgroup_local_max_events":cg["events_local"]["max"],
                           "cgroup_local_oom_events":cg["events_local"]["oom"],
                           "cgroup_local_oom_kill_events":cg["events_local"]["oom_kill"],
                           "rss_bytes":ps["VmRSS"],"proc_swap_bytes":ps["VmSwap"],
                           "gpu_used_mib":gpu["used_mib"],
                           "gpu_temperature_c":gpu["temperature_c"],
                           "cpu_tctl_c":th["cpu_tctl_c"],
                           "nvme_composite_c":th["nvme_composite_c"],
                           "mem_available_bytes":sample["mem_available_bytes"]})
    return {"schema_version":"c2-run-v1","campaign_id":protocol["campaign_id"],
            "run_id":config["run_id"],"protocol_id":protocol["protocol_id"],
            "identity":protocol["identity"],
            "expected_request_ids":protocol["expected_request_ids"],
            "requests":requests,"samples":normalized,"limits":protocol["limits"],
            "outcome":{"elapsed_s":elapsed,"returncode":returncode,
                       "stop_reasons":reasons,"backend_errors":backend_errors}}


def reserve(path):
    return open(path, "xb")


def loaded_backend_libraries(pid, backend):
    root = backend.resolve()
    found = {}
    for line in Path(f"/proc/{pid}/maps").read_text().splitlines():
        path = line.rsplit(" ",1)[-1]
        if not path.startswith("/") or " (deleted)" in line:
            continue
        candidate = Path(path).resolve()
        if candidate.is_file() and candidate.is_relative_to(root) and ".so" in candidate.name:
            found[str(candidate.relative_to(root))] = sha256(candidate)
    return found


def run(args, protocol, config, task_rows, model):
    cg_start = cgroup_state()
    if not cg_start or cg_start["memory_max"] != 18*2**30 or cg_start["swap_max"] != 0:
        raise GateError("18 GiB cgroup and zero swap not enforced")
    if model.stat().st_size <= 0 or mem_available() < 6*2**30:
        raise GateError("model or host headroom unavailable")
    if not gpu_state() or not thermal_state():
        raise GateError("required GPU or thermal sensors unavailable before launch")
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1",18367))
    stem = ROOT / "results" / args.run_id
    paths = {suffix:Path(str(stem)+suffix) for suffix in
             (".preflight.json",".json",".normalized.json",".stdout",".stderr",".samples.jsonl")}
    if any(path.exists() for path in paths.values()):
        raise GateError("run ID/output already exists")
    config = dict(config, run_id=args.run_id)
    total_timeout = config.get("total_timeout_s",3600)
    model_before = model.stat()
    preflight = {"schema_version":"c2-server-preflight-v1","run_id":args.run_id,
                 "protocol_sha256":sha256(args.protocol),"protocol":protocol,
                 "config":config,"model_path":str(model),"model_size_bytes":model.stat().st_size,
                 "model_sha256_prior_verified":protocol["identity"]["model_sha256"],
                 "model_stat_before":{"dev":model_before.st_dev,"ino":model_before.st_ino,
                                      "size":model_before.st_size,"mtime_ns":model_before.st_mtime_ns},
                 "runner_sha256":sha256(__file__),
                 "started_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
                 "cgroup_start":cg_start,"timeout_s":total_timeout}
    with open(paths[".preflight.json"],"x") as out:
        json.dump(preflight,out,indent=2,allow_nan=False);out.write("\n")
    t0 = time.monotonic()
    command = config["server_command"]
    env = os.environ.copy();env.update(config["explicit_env"])
    reasons = []
    raw = []
    samples = []
    stop = threading.Event()
    with reserve(paths[".stdout"]) as stdout, reserve(paths[".stderr"]) as stderr, \
         open(paths[".samples.jsonl"],"x") as sample_file:
        server = subprocess.Popen(command, stdout=stdout, stderr=stderr,
                                  env=env, start_new_session=True)
        def monitor():
            while not stop.is_set() and server.poll() is None:
                try:
                    collection_start = time.monotonic()
                    ps = proc_status(server.pid); cg = cgroup_state()
                    gpu = gpu_state(); th = thermal_state(); available = mem_available()
                    now = time.monotonic()-t0
                    sample = {"elapsed_s":now,"pid":server.pid,"proc":ps,"cgroup":cg,
                              "gpu":gpu,"thermal":th,"mem_available_bytes":available,
                              "model_fds":model_fd_state(server.pid,str(model)),
                              "collection_s":time.monotonic()-collection_start}
                    samples.append(sample)
                    sample_file.write(json.dumps(sample,allow_nan=False)+"\n");sample_file.flush()
                    reason = None
                    if now > total_timeout: reason = "TIMEOUT"
                    elif not ps or not cg or not gpu or not th or available is None: reason = "TELEMETRY_MISSING"
                    elif ps["VmSwap"] or cg["swap_current"]: reason = "SWAP_USED"
                    elif cg["events"]["oom"] > cg_start["events"]["oom"]: reason = "CGROUP_OOM"
                    elif cg["events"]["max"] > cg_start["events"]["max"]: reason = "CGROUP_LIMIT_HIT"
                    elif ps["VmRSS"] > 17*2**30: reason = "RSS_GUARD"
                    elif available < 6*2**30: reason = "HOST_HEADROOM_GUARD"
                    elif gpu["used_mib"] > 7000: reason = "GPU_GUARD"
                    elif th["cpu_tctl_c"] > 95 or gpu["temperature_c"] > 80 or th["nvme_composite_c"] > 70:
                        reason = "THERMAL_GUARD"
                    if reason:
                        reasons.append(reason);stop_own_server(server);break
                    stop.wait(1)
                except Exception as exc:
                    reasons.append(f"MONITOR_ERROR:{type(exc).__name__}:{exc}")
                    stop_own_server(server);break
        watcher = threading.Thread(target=monitor,daemon=True);watcher.start()
        try:
            ready = False
            while time.monotonic()-t0 < 90 and not reasons:
                if server.poll() is not None: raise GateError("server exited during load")
                try:
                    ready = fetch("/health",timeout=3).get("status") == "ok"
                except Exception:
                    pass
                if ready: break
                time.sleep(0.5)
            if not ready: raise GateError("readiness timeout")
            preflight["ready_elapsed_s"] = time.monotonic()-t0
            model_id = fetch("/v1/models")["data"][0]["id"]
            preflight["server_model_id"] = model_id
            loaded = loaded_backend_libraries(server.pid, ROOT/"backends"/MODEL[args.model][0])
            preflight["actually_loaded_backend_libraries_sha256"] = loaded
            if any(loaded.get(path) != digest_value for path,digest_value in
                   protocol["identity"]["library_sha256"].items()):
                raise GateError("loaded backend libraries differ from frozen identity")
            for row_id, task in task_rows:
                if reasons or server.poll() is not None: raise GateError("server/watchdog stopped")
                payload = {"model":model_id,"messages":[{"role":"user","content":task["prompt"]}],
                           "max_tokens":config["request_policy"]["max_tokens"],
                           "temperature":0,"seed":42,"stream":False}
                start = time.monotonic()-t0
                response = fetch("/v1/chat/completions",payload,
                                 timeout=config["request_policy"]["per_request_timeout_s"])
                end = time.monotonic()-t0
                choices = response.get("choices")
                if type(choices) is not list or len(choices) != 1 or type(choices[0].get("message")) is not dict:
                    raise GateError(f"missing assistant message for {row_id}")
                item = {"id":row_id,"source_task_id":task["id"],"category":task["category"],
                        "started_s":start,"ended_s":end,"finish_reason":choices[0].get("finish_reason"),
                        "usage":response.get("usage"),"timings":response.get("timings"),
                        "message":choices[0]["message"]}
                raw.append(item)
                print(json.dumps({"id":row_id,"elapsed_s":end-start,"usage":item["usage"]}),flush=True)
        except Exception as exc:
            reasons.append(f"RUN_ERROR:{type(exc).__name__}:{exc}")
        finally:
            # Keep sampling through graceful shutdown; ending the sampler first
            # left an unobserved >2 s process tail in the initial target smoke.
            stop_own_server(server);stop.set();watcher.join(timeout=5)
    ended = time.monotonic()-t0
    model_after = model.stat()
    if (model_after.st_dev,model_after.st_ino,model_after.st_size,model_after.st_mtime_ns) != \
       (model_before.st_dev,model_before.st_ino,model_before.st_size,model_before.st_mtime_ns):
        reasons.append("MODEL_IDENTITY_CHANGED")
    cg_end = cgroup_state()
    if not cg_end:
        reasons.append("CGROUP_END_MISSING")
    else:
        if cg_end["swap_current"] or cg_end["memory_peak"] > cg_end["memory_max"]:
            reasons.append("CGROUP_END_RESOURCE_VIOLATION")
        for name in ("events","events_local"):
            if any(cg_end[name][key] > cg_start[name][key] for key in ("max","oom","oom_kill")):
                reasons.append(f"CGROUP_END_{name.upper()}_EVENT")
    result = {"schema_version":"c2-server-raw-v1","preflight":preflight,
              "ended_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"elapsed_s":ended,
              "returncode":server.returncode,"stop_reasons":reasons,"results":raw,
              "cgroup_end":cg_end,"sample_count":len(samples),
              "source_sha256":{s:sha256(p) for s,p in paths.items() if s in
                               (".stdout",".stderr",".samples.jsonl") and p.exists()}}
    with open(paths[".json"],"x") as out:
        json.dump(result,out,indent=2,allow_nan=False);out.write("\n")
    if not reasons and len(raw) == len(task_rows) and server.returncode == 0:
        try:
            doc = normalize(raw,protocol,config,samples,paths[".stderr"].read_text(errors="replace"),
                            ended,server.returncode,reasons)
            with open(paths[".normalized.json"],"x") as out:
                json.dump(doc,out,indent=2,allow_nan=False);out.write("\n")
        except Exception as exc:
            reasons.append(f"NORMALIZATION_ERROR:{type(exc).__name__}:{exc}")
    print(json.dumps({"run_id":args.run_id,"completed":len(raw),"elapsed_s":ended,
                      "stop_reasons":reasons,"normalized":paths[".normalized.json"].exists()}),flush=True)
    return 0 if not reasons and paths[".normalized.json"].exists() else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model",required=True,choices=MODEL)
    p.add_argument("--suite",required=True,choices=("smoke1","historic20","c2core8"))
    p.add_argument("--ngl",type=int,default=8)
    p.add_argument("--ubatch",type=int,default=32)
    p.add_argument("--slots",type=int,default=32)
    p.add_argument("--protocol-id",required=True)
    p.add_argument("--protocol",required=True,type=Path)
    p.add_argument("--freeze-only",action="store_true")
    p.add_argument("--run-id")
    args = p.parse_args()
    if args.ngl < 0 or args.ubatch < 1 or args.slots < 1:
        p.error("invalid placement/batch/slots")
    protocol,config,tasks,model = configuration(args)
    if args.freeze_only:
        with open(args.protocol,"x") as out:
            json.dump(protocol,out,indent=2,allow_nan=False);out.write("\n")
        print(json.dumps({"frozen_protocol":str(args.protocol),"identity":protocol["identity"]}))
        return 0
    if not args.run_id:
        p.error("--run-id required for execution")
    if not re.fullmatch(r"[a-zA-Z0-9_-]+",args.run_id):
        p.error("invalid run ID")
    if strict_json(args.protocol.read_text()) != protocol:
        p.error("current binary/model/config/workload differs from frozen protocol")
    return run(args,protocol,config,tasks,model)


if __name__ == "__main__":
    raise SystemExit(main())
