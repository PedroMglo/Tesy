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
                         thermal_state, relevant_environment)
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
EVAL12_IDS = ("c2-eval-code-01", "c2-eval-code-02", "c2-eval-code-03",
              "c2-eval-sql-01", "c2-eval-sql-02", "c2-eval-sql-03",
              "c2-eval-quant-01", "c2-eval-quant-02",
              "c2-eval-plan-01", "c2-eval-plan-02",
              "c2-eval-spec-01", "c2-eval-spec-02")
C3_FOLLOWUP_IDS = ("c2-eval-code-02", "c2-eval-plan-01")
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
    if suite in ("historic20", "c3sustained20"):
        tasks = [json.loads(line) for line in HISTORIC.read_text().splitlines()]
        tasks = [x for x in tasks if x["split"] == "eval"]
        if len(tasks) != 10 or len({x["id"] for x in tasks}) != 10:
            raise GateError("historic eval suite is not ten unique tasks")
        return [(f"block{block}-{x['id']}", x) for block in (1, 2) for x in tasks], HISTORIC
    if suite in ("c2core8", "c2eval12", "c3followup2"):
        tasks = strict_json(C2_TASKS.read_text())["tasks"]
        found = {x["id"]:x for x in tasks}
        selected = CORE_IDS if suite == "c2core8" else \
                   C3_FOLLOWUP_IDS if suite == "c3followup2" else EVAL12_IDS
        if len(found) != len(tasks) or any(x not in found or found[x]["split"] != "eval" for x in selected):
            raise GateError("frozen C2 evaluation tasks unavailable")
        return [(x,found[x]) for x in selected], C2_TASKS
    raise GateError("unknown suite")


def configuration(args):
    if args.suite == "c3sustained20" and args.model != "target120b":
        raise GateError("C3 preload sustained suite requires target120b")
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
    explicit_env = {"LLAMA_MOE_STREAM_NO_PRELOAD":"1"} if \
                   args.model == "target120b" and args.suite != "c3sustained20" else {}
    task_rows, workload = tasks_for(args.suite)
    max_tokens = 64 if args.suite == "smoke1" else 512 if args.suite in ("historic20", "c3sustained20") else \
                 3072 if args.suite == "c3followup2" else 2048
    request_timeout = 180 if args.suite == "smoke1" else 360 if args.suite in ("historic20", "c3sustained20") else \
                      300 if args.suite == "c3followup2" else 1200
    policy = {"temperature":0,"seed":42,"max_tokens":max_tokens,"reasoning_effort":"medium",
              "attempts":1,"prompt_cache":False,"per_request_timeout_s":request_timeout}
    config = {"server_command":command,"explicit_env":explicit_env,"request_policy":policy,
              "suite":args.suite,"task_ids":[x[0] for x in task_rows]}
    if args.suite in ("c2core8", "c2eval12"):
        config["total_timeout_s"] = 7200 if args.suite == "c2core8" else 10800
    if args.suite == "c3followup2":
        config["total_timeout_s"] = 900
    if args.suite == "c3sustained20":
        config["preload_enabled"] = True
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
              "min_elapsed_s":900 if args.suite in ("historic20", "c3sustained20") else 0,
              "min_active_s":900 if args.suite in ("historic20", "c3sustained20") else 0,
              "min_decode_s":600 if args.suite in ("historic20", "c3sustained20") else 0,
              "min_decode_tok_s":3 if args.suite == "c3sustained20" else 2 if args.suite == "historic20" else 0,
              "min_last_half_tok_s":3 if args.suite == "c3sustained20" else 2 if args.suite == "historic20" else 0}
    protocol = {"schema_version":"c2-protocol-v1",
                "campaign_id":"tesy-c3-20260926" if args.suite in ("c3followup2", "c3sustained20") else "tesy-c2-20260926",
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
        cache_n = timing.get("cache_n")
        if type(cache_n) is not int or cache_n < 0 or \
           usage.get("prompt_tokens_details",{}).get("cached_tokens") != cache_n or \
           (not config.get("allow_cache_prompt", False) and cache_n != 0):
            raise GateError("prefix cache reuse differs from frozen protocol")
        if type(usage.get("prompt_tokens")) is not int or usage["prompt_tokens"] <= 0 or \
           type(usage.get("completion_tokens")) is not int or \
           not 0 < usage["completion_tokens"] <= config["request_policy"]["max_tokens"]:
            raise GateError("API token count missing or outside frozen request cap")
        if usage.get("total_tokens") != usage["prompt_tokens"]+usage["completion_tokens"]:
            raise GateError("API total token count inconsistent")
        if (config["suite"] in ("c2core8", "c2eval12", "c3followup2") or
            config.get("enforce_output_reserve", False)) and \
           usage["prompt_tokens"]+config["request_policy"]["max_tokens"] > config.get("n_ctx",4096):
            raise GateError("templated prompt did not leave the frozen output reserve")
        matches = [task_id for task_id, pair in parsed.items() if
                   pair["prompt eval"][0] + cache_n == usage.get("prompt_tokens") and
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
                         "backend_prompt_tokens":parsed[task_id]["prompt eval"][0] + cache_n,
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


def process_identity(pid):
    stat = Path(f"/proc/{pid}/stat").read_text()
    fields = stat[stat.rfind(")") + 2:].split()
    start_ticks = int(fields[19])  # field 22, after pid and comm
    cgroup = next(line.split("::", 1)[1].strip()
                  for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines()
                  if line.startswith("0::"))
    inode = (Path("/sys/fs/cgroup") / cgroup.lstrip("/")).stat().st_ino
    return {"pid": pid, "start_ticks": start_ticks,
            "cgroup_path": cgroup, "cgroup_inode": inode}


def child_exited_after_sample_loss(server):
    """Distinguish a normal terminal /proc race from missing live telemetry."""
    try:
        server.wait(timeout=0.2)
        return True
    except subprocess.TimeoutExpired:
        return False


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
    output_root = Path(config.get("output_root", ROOT / "results"))
    if not output_root.is_dir():
        raise GateError("server output root missing")
    stem = output_root / args.run_id
    paths = {suffix:Path(str(stem)+suffix) for suffix in
             (".preflight.json",".launch.json",".tokenization.json",".json",".normalized.json",".stdout",".stderr",".samples.jsonl")}
    if any(path.exists() for path in paths.values()):
        raise GateError("run ID/output already exists")
    config = dict(config, run_id=args.run_id)
    total_timeout = config.get("total_timeout_s",3600)
    model_before = model.stat()
    env = os.environ.copy();env.update(config["explicit_env"])
    if args.suite == "c3sustained20":
        env.pop("LLAMA_MOE_STREAM_NO_PRELOAD", None)
    preflight = {"schema_version":"c2-server-preflight-v1","run_id":args.run_id,
                 "protocol_sha256":sha256(args.protocol),"protocol":protocol,
                 "config":config,"model_path":str(model),"model_size_bytes":model.stat().st_size,
                 "model_sha256_prior_verified":protocol["identity"]["model_sha256"],
                 "model_stat_before":{"dev":model_before.st_dev,"ino":model_before.st_ino,
                                      "size":model_before.st_size,"mtime_ns":model_before.st_mtime_ns},
                 "runner_sha256":sha256(__file__),
                 "started_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
                 "cgroup_start":cg_start,"timeout_s":total_timeout,
                 "relevant_environment":relevant_environment(env)}
    with open(paths[".preflight.json"],"x") as out:
        json.dump(preflight,out,indent=2,allow_nan=False);out.write("\n")
    t0 = time.monotonic()
    command = config["server_command"]
    reasons = []
    raw = []
    samples = []
    stop = threading.Event()
    c18_request_active = threading.Event()
    with reserve(paths[".stdout"]) as stdout, reserve(paths[".stderr"]) as stderr, \
         open(paths[".samples.jsonl"],"x") as sample_file:
        server = subprocess.Popen(command, stdout=stdout, stderr=stderr,
                                  env=env, start_new_session=True)
        try:
            launch = {"schema_version":"c3-launch-v1", "run_id":args.run_id,
                      "process_identity":process_identity(server.pid),
                      "cgroup_start":cg_start, "preflight_sha256":sha256(paths[".preflight.json"])}
            if launch["process_identity"]["cgroup_path"] != cg_start["path"]:
                raise GateError("model process is outside the preflight cgroup")
            with open(paths[".launch.json"],"x") as out:
                json.dump(launch,out,indent=2,allow_nan=False);out.write("\n")
            preflight["launch_identity"] = launch["process_identity"]
        except Exception:
            stop_own_server(server)
            raise
        def monitor():
            previous_cpu_diag = None
            previous_cpu_diag_t = None
            prewarning_clocks = []
            warning_clocks = []
            while not stop.is_set() and server.poll() is None:
                try:
                    collection_start = time.monotonic()
                    ps = proc_status(server.pid); cg = cgroup_state()
                    gpu = gpu_state(); th = thermal_state(); available = mem_available()
                    now = time.monotonic()-t0
                    cpu_diag = None
                    if protocol.get('c18'):
                        from c18_cpu_telemetry import capture, package_power_w
                        cpu_diag = capture()
                        cpu_diag['package_power_w'] = package_power_w(
                            previous_cpu_diag, cpu_diag,
                            now - previous_cpu_diag_t if previous_cpu_diag_t is not None else 0)
                        previous_cpu_diag, previous_cpu_diag_t = cpu_diag, now
                        cpu_diag['thermal_warning'] = th['cpu_tctl_c'] >= 95
                        cpu_diag['request_active'] = c18_request_active.is_set()
                        if cpu_diag['request_active'] and th['cpu_tctl_c'] < 90 and \
                                cpu_diag['package_power_w'] is not None and cpu_diag['package_power_w'] > 10:
                            prewarning_clocks.append(cpu_diag['effective_clock_median_mhz'])
                        if cpu_diag['request_active'] and th['cpu_tctl_c'] >= 95:
                            warning_clocks.append(cpu_diag['effective_clock_median_mhz'])
                        else:
                            warning_clocks.clear()
                    try:
                        identity = process_identity(server.pid)
                    except (FileNotFoundError, ProcessLookupError):
                        # /proc may disappear after the poll above. Skip the
                        # terminal partial sample only after the child exits.
                        if not child_exited_after_sample_loss(server):
                            reasons.append("TELEMETRY_MISSING_LIVE_PROCESS")
                            stop_own_server(server)
                        break
                    if not ps or any(field not in ps for field in ("VmRSS", "VmSwap", "VmHWM")):
                        if not child_exited_after_sample_loss(server):
                            reasons.append("TELEMETRY_MISSING_LIVE_PROCESS")
                            stop_own_server(server)
                        break
                    sample = {"elapsed_s":now,"pid":server.pid,
                              "process_identity":identity,
                              "proc":ps,"cgroup":cg,
                              "gpu":gpu,"thermal":th,"mem_available_bytes":available,
                              "model_fds":model_fd_state(server.pid,str(model)),
                              "collection_s":time.monotonic()-collection_start}
                    if cpu_diag is not None:
                        sample['cpu_diagnostics'] = cpu_diag
                    samples.append(sample)
                    sample_file.write(json.dumps(sample,allow_nan=False)+"\n");sample_file.flush()
                    reason = None
                    if now > total_timeout: reason = "TIMEOUT"
                    elif not ps or not cg or not gpu or not th or available is None: reason = "TELEMETRY_MISSING"
                    elif ps["VmSwap"] or cg["swap_current"]: reason = "SWAP_USED"
                    elif cg["events"]["oom"] > cg_start["events"]["oom"]: reason = "CGROUP_OOM"
                    elif cg["events"]["max"] > cg_start["events"]["max"]: reason = "CGROUP_LIMIT_HIT"
                    elif ps["VmRSS"] > protocol["limits"]["rss_max_bytes"]: reason = "RSS_GUARD"
                    elif cg["memory_peak"] > protocol["limits"]["memory_max_bytes"]: reason = "CGROUP_RESERVE_GUARD"
                    elif available < protocol["limits"]["min_mem_available_bytes"]: reason = "HOST_HEADROOM_GUARD"
                    elif gpu["used_mib"] > protocol["limits"]["gpu_max_mib"]: reason = "GPU_GUARD"
                    elif protocol.get('c18'):
                        from c18_cpu_telemetry import thermal_stop_reason
                        reason = thermal_stop_reason(th['cpu_tctl_c'], cpu_diag,
                                                     prewarning_clocks, warning_clocks)
                        if reason is None and (gpu["temperature_c"] > protocol["limits"]["gpu_max_c"] or
                                               th["nvme_composite_c"] > protocol["limits"]["nvme_max_c"]):
                            reason = "THERMAL_GUARD"
                    elif th["cpu_tctl_c"] > protocol["limits"]["cpu_max_c"] or \
                         gpu["temperature_c"] > protocol["limits"]["gpu_max_c"] or \
                         th["nvme_composite_c"] > protocol["limits"]["nvme_max_c"]:
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
            loaded = loaded_backend_libraries(server.pid,
                                              Path(config.get("backend_root", ROOT/"backends"/MODEL[args.model][0])))
            preflight["actually_loaded_backend_libraries_sha256"] = loaded
            if any(loaded.get(path) != digest_value for path,digest_value in
                   protocol["identity"]["library_sha256"].items()):
                raise GateError("loaded backend libraries differ from frozen identity")
            if args.suite in ("c2core8", "c2eval12", "c3followup2") or config.get("pretokenize",False):
                tokenization = {}
                token_ids = {}
                for row_id, task in task_rows:
                    messages = task.get("messages") or [{"role":"user","content":task["prompt"]}]
                    template = fetch("/apply-template",{"model":model_id,
                                      "messages":messages,
                                      "max_tokens":config["request_policy"]["max_tokens"],
                                      "temperature":0,"seed":42})
                    if type(template.get("prompt")) is not str:
                        raise GateError(f"official template unavailable for {row_id}")
                    tokenized = fetch("/tokenize",{"content":template["prompt"],
                                       "add_special":False,"parse_special":True})
                    ids = tokenized.get("tokens")
                    if type(ids) is not list or any(type(x) is not int for x in ids) or \
                       not 0 < len(ids) <= config.get("n_ctx",4096)-config["request_policy"]["max_tokens"]:
                        raise GateError(f"official tokenization exceeds output reserve for {row_id}")
                    bounds = config.get("prompt_token_ranges",{}).get(row_id)
                    if bounds and not bounds[0] <= len(ids) <= bounds[1]:
                        raise GateError(f"official tokenization outside frozen range for {row_id}")
                    tokenization[row_id] = {"count":len(ids),"token_ids_sha256":digest(ids)}
                    token_ids[row_id] = ids
                preflight["prompt_tokenization"] = tokenization
                if config.get("freeze_token_ids",False):
                    with open(paths[".tokenization.json"],"x") as out:
                        json.dump(token_ids,out,indent=2,allow_nan=False);out.write("\n")
            for row_id, task in task_rows:
                if reasons or server.poll() is not None: raise GateError("server/watchdog stopped")
                messages = task.get("messages") or [{"role":"user","content":task["prompt"]}]
                payload = {"model":model_id,"messages":messages,
                           "max_tokens":config["request_policy"]["max_tokens"],
                           "temperature":0,"seed":42,"stream":False}
                if "cache_prompt" in task:
                    payload["cache_prompt"] = task["cache_prompt"]
                start = time.monotonic()-t0
                if protocol.get('c18'):
                    c18_request_active.set()
                response = fetch("/v1/chat/completions",payload,
                                 timeout=config["request_policy"]["per_request_timeout_s"])
                end = time.monotonic()-t0
                if protocol.get('c18'):
                    c18_request_active.clear()
                choices = response.get("choices")
                if type(choices) is not list or len(choices) != 1 or type(choices[0].get("message")) is not dict:
                    raise GateError(f"missing assistant message for {row_id}")
                if (args.suite in ("c2core8", "c2eval12", "c3followup2") or
                    config.get("pretokenize",False)) and \
                   response.get("usage",{}).get("prompt_tokens") != \
                   preflight["prompt_tokenization"][row_id]["count"]:
                    raise GateError(f"API prompt count differs from preflight tokenizer for {row_id}")
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
              "launch_identity":launch["process_identity"],
              "source_sha256":{s:sha256(p) for s,p in paths.items() if s in
                               (".launch.json",".tokenization.json",".stdout",".stderr",".samples.jsonl") and p.exists()}}
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
    p.add_argument("--suite",required=True,choices=("smoke1","historic20","c2core8","c2eval12","c3followup2","c3sustained20"))
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
