#!/usr/bin/env python3
"""Frozen C2 localhost server run; reuse run_task_server and run_bounded primitives."""

import argparse
from contextlib import nullcontext
import ctypes
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import threading
import time
from urllib.request import Request, urlopen

from c2_gate import GateError, strict_json
from run_bounded import (backend_library_hashes, cgroup_state, gpu_state,
                         mem_available, model_fd_state, proc_status, sha256,
                         thermal_state, relevant_environment)
from run_task_server import PORT, fetch, stop_own_server
from request_evidence import Deadline, Evidence

_REQUEST_LOCAL = threading.local()


_LIBC = ctypes.CDLL(None, use_errno=True)
_LIBC.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                       ctypes.c_ulong, ctypes.c_ulong]
_LIBC.prctl.restype = ctypes.c_int


def parent_death_guard(parent_pid):
    """Stop our server if the runner dies, including a fork-to-prctl race."""
    def arm():
        if _LIBC.prctl(1, int(signal.SIGTERM), 0, 0, 0) != 0 or \
           os.getppid() != parent_pid:
            os._exit(127)
    return arm


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


def task_template_kwargs(task):
    if 'chat_template_kwargs' not in task:
        return {}
    value = task['chat_template_kwargs']
    if type(value) is not dict or not value or any(type(key) is not str for key in value):
        raise GateError('chat template kwargs must be a nonempty string-keyed object')
    json_bytes(value)
    return {'chat_template_kwargs': value}


def session_idle_seconds(config):
    value = config.get('inter_request_idle_s', 0)
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 600:
        raise GateError('invalid inter-request idle duration')
    return float(value)


def session_idle_schedule(config, request_count):
    """Idle before each request; index zero is always zero."""
    fallback = session_idle_seconds(config)
    schedule = config.get('inter_request_idle_schedule_s')
    if schedule is None:
        return [0.0] + [fallback] * (request_count - 1)
    if type(schedule) is not list or len(schedule) != request_count or \
       not schedule or schedule[0] != 0:
        raise GateError('invalid inter-request idle schedule shape')
    values = []
    for value in schedule:
        if type(value) not in (int, float) or not math.isfinite(value) or \
           not 0 <= value <= 600:
            raise GateError('invalid inter-request idle schedule value')
        values.append(float(value))
    return values


def require_natural_completion(item, max_tokens):
    """Reject capped or incomplete output after retaining the response in raw."""
    if type(max_tokens) is not int or max_tokens <= 0 or \
       type(item.get('usage')) is not dict or \
       type(item['usage'].get('completion_tokens')) is not int or \
       item.get('finish_reason') != 'stop' or \
       not 0 < item['usage']['completion_tokens'] < max_tokens:
        raise GateError(f"output capped or incomplete for {item.get('id')}")


def validate_adjacent_cache(previous_ids, current_ids, cache_n, min_common, max_lost=None):
    common = next((i for i, (a, b) in enumerate(zip(previous_ids, current_ids))
                   if a != b), min(len(previous_ids), len(current_ids)))
    if type(cache_n) is not int or common < min_common or \
            (max_lost is not None and common < len(previous_ids) - max_lost) or \
            not common - 32 <= cache_n <= common:
        raise GateError('adjacent exact-prefix cache outside frozen band')
    return common


def validate_generated_prefix_cache(previous_ids, current_ids, cache_n,
                                    prompt_n, previous_completion_n,
                                    min_common, max_lost=32):
    """Bound a live history cache, which may include prior generated tokens."""
    common = next((i for i, (a, b) in enumerate(zip(previous_ids, current_ids))
                   if a != b), min(len(previous_ids), len(current_ids)))
    upper = min(len(current_ids), common + previous_completion_n)
    if (type(cache_n) is not int or type(prompt_n) is not int or
        type(previous_completion_n) is not int or previous_completion_n <= 0 or
        common < min_common or len(previous_ids)-common > max_lost or
        not common-32 <= cache_n <= upper or
        prompt_n + cache_n != len(current_ids)):
        raise GateError('generated-token prefix cache outside frozen band')
    return common


def parse_chat_stream(lines, elapsed):
    """Collect one OpenAI chat SSE response and timestamp received text chunks."""
    content = []
    reasoning = []
    first_text = first_reasoning = first_final = None
    finish_reason = usage = timings = None
    event_count = 0
    done = False
    for raw_line in lines:
        line = raw_line.decode('utf-8').strip() if isinstance(raw_line, bytes) else raw_line.strip()
        if not line.startswith('data: '):
            continue
        data = line[6:]
        if data == '[DONE]':
            done = True
            break
        event = strict_json(data)
        if type(event) is not dict or type(event.get('choices')) is not list:
            raise GateError('malformed chat stream event')
        event_count += 1
        choices = event['choices']
        if len(choices) > 1:
            raise GateError('unexpected multiple stream choices')
        if choices:
            choice = choices[0]
            if type(choice) is not dict or type(choice.get('delta')) is not dict:
                raise GateError('malformed stream delta')
            delta = choice['delta']
            if delta.get('tool_calls'):
                raise GateError('tool call outside frozen stream workload')
            for key, target in (('reasoning_content', reasoning), ('content', content)):
                chunk = delta.get(key, '')
                if chunk is None:
                    continue  # server-task.cpp sends content:null in the initial role event
                if type(chunk) is not str:
                    raise GateError('non-string stream text')
                if chunk:
                    target.append(chunk)
                    if chunk.strip():
                        timestamp = elapsed()
                        if first_text is None:
                            first_text = timestamp
                        if key == 'reasoning_content' and first_reasoning is None:
                            first_reasoning = timestamp
                        if key == 'content' and first_final is None:
                            first_final = timestamp
            if choice.get('finish_reason') is not None:
                if finish_reason is not None or type(choice['finish_reason']) is not str:
                    raise GateError('duplicate/invalid stream finish reason')
                finish_reason = choice['finish_reason']
        if 'usage' in event:
            if usage is not None or type(event['usage']) is not dict:
                raise GateError('duplicate/invalid stream usage')
            usage = event['usage']
        if 'timings' in event:
            if timings is not None or type(event['timings']) is not dict:
                raise GateError('duplicate/invalid stream timings')
            timings = event['timings']
    if not done or finish_reason not in ('stop', 'length') or usage is None or timings is None:
        raise GateError('incomplete stream completion/usage/timings fence')
    message = {'role': 'assistant', 'content': ''.join(content)}
    if reasoning:
        message['reasoning_content'] = ''.join(reasoning)
    response = {'choices': [{'message': message, 'finish_reason': finish_reason}],
                'usage': usage, 'timings': timings}
    metrics = {'first_text_chunk_s': first_text,
               'first_reasoning_chunk_s': first_reasoning,
               'first_final_content_chunk_s': first_final,
               'sse_event_count': event_count, 'done_observed': done,
               'interpretation': 'client receipt times of non-whitespace SSE chunks; not token timestamps'}
    return response, metrics


def stream_chat(payload, timeout, started_monotonic, base_url=None):
    req = Request((base_url or f'http://127.0.0.1:{PORT}')+'/v1/chat/completions',
                  data=json.dumps(payload, allow_nan=False).encode(),
                  headers={'Content-Type': 'application/json'}, method='POST')
    with urlopen(req, timeout=timeout) as response:
        if response.status != 200:
            raise GateError('chat stream HTTP status not 200')
        def observed():
            for line in response:
                evidence = getattr(_REQUEST_LOCAL, 'evidence', None)
                if evidence is not None:
                    evidence.write('SSE_FRAGMENT', fragment=line.decode('utf-8', errors='replace'))
                yield line
        return parse_chat_stream(observed(),
                                 lambda: time.monotonic() - started_monotonic)


def validate_token_relationships(token_ids, relationships):
    for relation in relationships:
        first = token_ids[relation['first']]
        second = token_ids[relation['second']]
        common = 0
        for a, b in zip(first, second):
            if a != b:
                break
            common += 1
        if len(second) - len(first) != relation['expected_delta'] or \
                common < relation['min_common']:
            raise GateError('frozen incremental token count/common prefix invalid')


def validate_expected_message(message, task):
    expected = task.get('expected_message_sha256')
    if expected is None:
        return
    if type(expected) is not str or not re.fullmatch(r'[0-9a-f]{64}', expected) or \
            digest(message) != expected:
        raise GateError('assistant message differs from frozen conversation turn')


def assistant_history_messages(first_messages, assistant_message, followup_messages):
    """Append an actual answer and user turn to an alternating session history."""
    if (type(first_messages) is not list or not first_messages or
        len(first_messages) % 2 != 1 or
        any(type(message) is not dict or
            message.get('role') != ('user' if index % 2 == 0 else 'assistant') or
            type(message.get('content')) is not str or not message['content']
            for index, message in enumerate(first_messages)) or
        type(followup_messages) is not list or len(followup_messages) != 1 or
        type(followup_messages[0]) is not dict or followup_messages[0].get('role') != 'user' or
        type(followup_messages[0].get('content')) is not str or
        type(assistant_message) is not dict or assistant_message.get('role') != 'assistant' or
        type(assistant_message.get('content')) is not str or not assistant_message['content']):
        raise GateError('actual assistant-history turn unavailable')
    return [dict(message) for message in first_messages] + [
            {'role': 'assistant', 'content': assistant_message['content']},
            dict(followup_messages[0])]


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
    from run_bounded import mapped_backend_libraries
    return mapped_backend_libraries(pid, backend)


def prospective_server_start_scope(protocol, current, contract):
    if contract.get('execution_class') == 'FILE_PAGING' and current.get('memory_high') != contract['cgroup']['memory_high_bytes']:
        raise GateError('prospective server memory.high differs from authority')
    unit = protocol.get('execution_scope_unit')
    if unit and not current.get('path', '').endswith('/'+unit+'.service'):
        raise GateError('prospective server scope differs from authority')


def server_endpoint_reasons(end, start, contract=None):
    if not end:
        return ['CGROUP_END_MISSING']
    if contract is not None:
        from run_bounded import prospective_endpoint_reason
        # Cadence is independently checked against the saved samples by the gate.
        reason = prospective_endpoint_reason(0, 0, 0, end, start, contract)
        return [] if reason is None else [reason]
    reasons = []
    if end['swap_current'] or end['memory_peak'] > end['memory_max']:
        reasons.append('CGROUP_END_RESOURCE_VIOLATION')
    for name in ('events','events_local'):
        if any(end[name][key] > start[name][key] for key in ('max','oom','oom_kill')):
            reasons.append('CGROUP_END_'+name.upper()+'_EVENT')
    return reasons


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


def protocol_cgroup_memory_max(protocol):
    """Return the frozen cgroup hard cap without assuming every campaign is E18."""
    if 'resources' in protocol:
        from host_resource_policy import validate_resource_protocol
        return validate_resource_protocol(protocol)['cgroup']['memory_max_bytes']
    values = []
    for value in protocol.values():
        if type(value) is dict and 'cgroup_memory_max_bytes' in value:
            cap = value['cgroup_memory_max_bytes']
            if type(cap) is not int or cap <= 0:
                raise GateError('invalid frozen cgroup memory cap')
            values.append(cap)
    if len(set(values)) > 1:
        raise GateError('conflicting frozen cgroup memory caps')
    return values[0] if values else 18 * 2**30


def per_task_request_policy(config, row_id):
    """Optional frozen task overrides; historical global policy remains default."""
    overrides = config.get('per_task_request_policy', {})
    if type(overrides) is not dict or any(k not in config.get('task_ids', []) for k in overrides):
        raise GateError('per-task request policy identity invalid')
    for value in overrides.values():
        if type(value) is not dict or set(value) - {'max_tokens', 'per_request_timeout_s'}:
            raise GateError('per-task request policy fields invalid')
        if 'max_tokens' in value and (type(value['max_tokens']) is not int or value['max_tokens'] <= 0):
            raise GateError('per-task max_tokens invalid')
        if 'per_request_timeout_s' in value and (type(value['per_request_timeout_s']) not in (int, float) or not math.isfinite(value['per_request_timeout_s']) or value['per_request_timeout_s'] <= 0):
            raise GateError('per-task deadline invalid')
    return dict(config['request_policy'], **overrides.get(row_id, {}))


def run(args, protocol, config, task_rows, model, *, result_validator=None):
    readiness_timeout = config.get('readiness_timeout_s', 90)
    if type(readiness_timeout) not in (int, float) or not math.isfinite(readiness_timeout) or readiness_timeout <= 0:
        raise GateError('readiness deadline invalid')
    for row_id, _ in task_rows:
        per_task_request_policy(config, row_id)
    prospective = 'resources' in protocol
    request_markers = config.get('record_monotonic_request_markers', False)
    trace_contract = protocol.get('trace')
    if type(request_markers) is not bool or (request_markers and
       (not prospective or type(trace_contract) is not dict or
        trace_contract.get('request_marker_schema') != 'c85-request-monotonic-v1')):
        raise GateError('unfrozen or invalid monotonic request marker contract')
    if prospective:
        from host_resource_policy import (RuntimeGuard, validate_resource_protocol,
                                          validate_start_observation,
                                          live_power, host_pressure)
        resource_contract = validate_resource_protocol(protocol)
    idle_schedule = session_idle_schedule(config, len(task_rows))
    require_natural = config.get('require_natural_stop', False)
    if type(require_natural) is not bool:
        raise GateError('require_natural_stop must be boolean')
    dynamic_history = config.get('append_previous_assistant_to_next', False)
    if dynamic_history is not False and dynamic_history is not True:
        raise GateError('invalid assistant-history flag')
    if dynamic_history and (not 2 <= len(task_rows) <= 20 or not config.get('pretokenize') or
                            not config.get('freeze_token_ids')):
        raise GateError('assistant-history requires 2-20 officially tokenized turns')
    minimum = config.get('adjacent_cache_min_common')
    if minimum is not None and (type(minimum) is not int or minimum <= 0 or
                                not config.get('pretokenize')):
        raise GateError('adjacent cache gate requires a positive bound and official tokens')
    max_lost = config.get('adjacent_prefix_tail_max')
    if max_lost is not None and (minimum is None or type(max_lost) is not int or
                                 not 0 <= max_lost <= 128):
        raise GateError('invalid adjacent-prefix tail bound')
    expected_cgroup_max = protocol_cgroup_memory_max(protocol)
    cg_start = cgroup_state()
    if not cg_start or cg_start["memory_max"] != expected_cgroup_max or cg_start["swap_max"] != 0:
        raise GateError("frozen cgroup cap and zero swap not enforced")
    if prospective:
        prospective_server_start_scope(protocol, cg_start, resource_contract)
    available_start = mem_available()
    minimum_available = (resource_contract['memory']['reserve_bytes'] if prospective
                         else 6*2**30)
    if model.stat().st_size <= 0 or available_start is None or available_start < minimum_available:
        raise GateError("model or host headroom unavailable")
    gpu_start = gpu_state(prospective=prospective)
    thermal_start = thermal_state(prospective=prospective)
    if not gpu_start or not thermal_start:
        raise GateError("required GPU or thermal sensors unavailable before launch")
    if prospective:
        power_start=live_power()
        psi_start=host_pressure()
        start_reasons=validate_start_observation(
            protocol,available_bytes=available_start,gpu=gpu_start,
            thermal=thermal_start,power=power_start,psi_full_avg10=psi_start)
        if start_reasons:
            raise GateError('prospective start admission: '+','.join(start_reasons))
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1",18367))
    output_root = Path(config.get("output_root", ROOT / "results"))
    if not output_root.is_dir():
        raise GateError("server output root missing")
    stem = output_root / args.run_id
    paths = {suffix:Path(str(stem)+suffix) for suffix in
             (".preflight.json",".launch.json",".tokenization.json",".json",".normalized.json",".stdout",".stderr",".samples.jsonl")}
    if request_markers:
        paths['.request-markers.jsonl'] = Path(str(stem) + '.request-markers.jsonl')
    trace_trigger_id = config.get('trace_trigger_request_id')
    if trace_trigger_id is not None:
        trigger = Path(config.get('explicit_env', {}).get('TESY_C122_TRACE_TRIGGER_FILE', ''))
        if not request_markers or not trace_contract or \
           trace_contract.get('expert_trace_schema') != 'c122-expert-decode-v1' or \
           trace_trigger_id not in [row_id for row_id, _ in task_rows] or \
           not trigger.is_absolute() or trigger.parent != output_root.resolve() or \
           trigger.name != args.run_id + '.trace-trigger.json':
            raise GateError('unfrozen C122 trace trigger identity')
        paths['.trace-trigger.json'] = trigger
    if any(path.exists() for path in paths.values()):
        raise GateError("run ID/output already exists")
    config = dict(config, run_id=args.run_id)
    total_timeout = config.get("total_timeout_s",3600)
    model_before = model.stat()
    env = os.environ.copy();env.update(config["explicit_env"])
    parallel_launch = None
    token_ids = {}
    if protocol.get('parallel_runtime') is not None:
        from parallel_runtime import validate_launch_runtime
        parallel_launch = validate_launch_runtime(protocol['parallel_runtime'], env)
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
    if prospective:
        preflight['resource_start_observation']={
            'mem_available_bytes':available_start,'gpu':gpu_start,'thermal':thermal_start,
            'power':power_start,'host_psi_full_avg10':psi_start,
            'admission_reasons':start_reasons}
    if parallel_launch is not None:
        preflight['parallel_runtime_at_launch'] = parallel_launch
    if request_markers:
        preflight['trace_clock'] = 'CLOCK_MONOTONIC; request marker ns and backend ggml_time_us share host clock'
    with open(paths[".preflight.json"],"x") as out:
        json.dump(preflight,out,indent=2,allow_nan=False);out.write("\n")
    t0 = time.monotonic()
    command = config["server_command"]
    reasons = []
    raw = []
    samples = []
    stop = threading.Event()
    c18_request_active = threading.Event()
    request_watchdog = None
    evidence = None
    current_item = None
    resource_gate = RuntimeGuard(protocol,cg_start) if prospective else None
    marker_context = (open(paths['.request-markers.jsonl'], 'x') if request_markers
                      else nullcontext())
    with reserve(paths[".stdout"]) as stdout, reserve(paths[".stderr"]) as stderr, \
         open(paths[".samples.jsonl"],"x") as sample_file, marker_context as marker_file:
        start_inventory = None
        if 'start_inventory' in protocol:
            from c118_start_inventory import require_inventory
            contract = protocol['start_inventory']
            if type(contract) is not dict or contract.get('schema') != 'c120-start-inventory-v1' or \
               contract.get('duration_s') != 60 or contract.get('max_age_s') != 3 or \
               output_root.name != 'raw':
                raise GateError('frozen start inventory contract invalid')
            inventory_root = output_root.parent
            policy_path = inventory_root / 'resource-policy.json'
            receipt_path = output_root / f'{args.run_id}.start-inventory.receipt.json'
            if sha256(policy_path) != contract.get('policy_sha256'):
                raise GateError('start inventory policy SHA changed')
            policy = strict_json(policy_path.read_text())
            receipt = strict_json(receipt_path.read_text())
            power = {'source':policy['power']['source'],
                     'profile':policy['power']['profile']}
            checked_utc = dt.datetime.now(dt.timezone.utc)
            require_inventory(inventory_root, args.run_id, receipt, policy=policy,
                              cap_bytes=expected_cgroup_max, expected_power=power,
                              duration_s=60, now=checked_utc, max_age_s=3)
            invoked_utc = dt.datetime.now(dt.timezone.utc)
            age = (invoked_utc-dt.datetime.fromisoformat(receipt['last_utc'])).total_seconds()
            if not 0 <= age <= 3:
                raise GateError('start inventory stale at process creation')
            start_inventory = {'receipt_sha256':sha256(receipt_path),
                               'checked_utc':checked_utc.isoformat(),
                               'popen_invoked_utc':invoked_utc.isoformat(),
                               'popen_invoked_monotonic_ns':time.monotonic_ns()}
        server = subprocess.Popen(command, stdout=stdout, stderr=stderr,
                                  env=env, start_new_session=True,
                                  preexec_fn=parent_death_guard(os.getpid()))
        owned_identity = process_identity(server.pid)
        cleanup_lock = threading.Lock()
        def stop_server():
            # Only our exact child may be signalled; recheck before escalation.
            with cleanup_lock:
                if server.poll() is not None:
                    return
                if process_identity(server.pid) != owned_identity:
                    raise GateError('PROCESS_IDENTITY_CHANGED_BEFORE_CANCEL')
                os.killpg(server.pid, signal.SIGTERM)
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if process_identity(server.pid) != owned_identity:
                        raise GateError('PROCESS_IDENTITY_CHANGED_BEFORE_KILL')
                    os.killpg(server.pid, signal.SIGKILL)
                    server.wait(timeout=1)
        try:
            launch = {"schema_version":"c3-launch-v1", "run_id":args.run_id,
                      "process_identity":process_identity(server.pid),
                      "cgroup_start":cg_start, "preflight_sha256":sha256(paths[".preflight.json"])}
            if start_inventory is not None:
                launch['start_inventory'] = start_inventory
            if launch["process_identity"]["cgroup_path"] != cg_start["path"]:
                raise GateError("model process is outside the preflight cgroup")
            with open(paths[".launch.json"],"x") as out:
                json.dump(launch,out,indent=2,allow_nan=False);out.write("\n")
            preflight["launch_identity"] = launch["process_identity"]
        except Exception:
            stop_server()
            raise
        def monitor():
            previous_cpu_diag = None
            previous_cpu_diag_t = None
            prewarning_clocks = []
            warning_clocks = []
            missing_since = None
            while not stop.is_set() and server.poll() is None:
                try:
                    collection_start = time.monotonic()
                    ps = proc_status(server.pid); cg = cgroup_state()
                    gpu = gpu_state(prospective=prospective)
                    th = thermal_state(prospective=prospective)
                    available = mem_available()
                    if prospective and (not gpu or not th or available is None):
                        gpu = gpu_state(prospective=True)
                        th = thermal_state(prospective=True)
                        available = mem_available()
                    now = time.monotonic()-t0
                    if prospective and (not gpu or not th or available is None):
                        missing_since = now if missing_since is None else missing_since
                        if now-missing_since >= resource_contract['telemetry']['loss_persistence_s']:
                            reasons.append('TELEMETRY_MISSING_PERSISTED')
                            stop_server();break
                        stop.wait(0.5);continue
                    missing_since = None
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
                            stop_server()
                        break
                    if identity != launch['process_identity']:
                        reasons.append('PROCESS_IDENTITY_CHANGED')
                        stop_server()
                        break
                    if not ps or any(field not in ps for field in ("VmRSS", "VmSwap", "VmHWM")):
                        if not child_exited_after_sample_loss(server):
                            reasons.append("TELEMETRY_MISSING_LIVE_PROCESS")
                            stop_server()
                        break
                    sample = {"elapsed_s":now,"pid":server.pid,
                              "process_identity":identity,
                              "proc":ps,"cgroup":cg,
                              "gpu":gpu,"thermal":th,"mem_available_bytes":available,
                              "model_fds":model_fd_state(server.pid,str(model)),
                              "collection_s":time.monotonic()-collection_start}
                    if prospective:
                        sample['resource_observation'] = {
                            'host_psi_full_avg10':host_pressure(),
                            'power':live_power()}
                    if cpu_diag is not None:
                        sample['cpu_diagnostics'] = cpu_diag
                    if protocol.get('optional_cpu_telemetry'):
                        from parallel_runtime import optional_cpu_observation
                        sample['optional_cpu_observation'] = optional_cpu_observation()
                    samples.append(sample)
                    sample_file.write(json.dumps(sample,allow_nan=False)+"\n");sample_file.flush()
                    reason = None
                    if now > total_timeout: reason = "TIMEOUT"
                    elif not ps or not cg or not gpu or not th or available is None: reason = "TELEMETRY_MISSING"
                    elif prospective:
                        reason = resource_gate.check(sample)
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
                        reasons.append(reason);stop_server();break
                    stop.wait(1)
                except Exception as exc:
                    reasons.append(f"MONITOR_ERROR:{type(exc).__name__}:{exc}")
                    stop_server();break
        watcher = threading.Thread(target=monitor,daemon=True);watcher.start()
        try:
            ready = False
            while time.monotonic()-t0 < readiness_timeout and not reasons:
                if server.poll() is not None: raise GateError("server exited during load")
                try:
                    ready = fetch("/health",timeout=3).get("status") == "ok"
                except Exception:
                    pass
                if ready: break
                time.sleep(0.5)
            if not ready or time.monotonic()-t0 >= readiness_timeout: raise GateError("readiness timeout")
            preflight["ready_elapsed_s"] = time.monotonic()-t0
            model_id = fetch("/v1/models")["data"][0]["id"]
            preflight["server_model_id"] = model_id
            loaded = loaded_backend_libraries(server.pid,
                                              Path(config.get("backend_root", ROOT/"backends"/MODEL[args.model][0])))
            preflight["actually_loaded_backend_libraries_sha256"] = loaded
            if loaded != protocol["identity"]["library_sha256"]:
                raise GateError("loaded backend libraries differ from frozen identity")
            if parallel_launch is not None:
                from parallel_runtime import mapped_parallel_runtime
                preflight['actually_loaded_parallel_runtime'] = mapped_parallel_runtime(server.pid, protocol['parallel_runtime'])
            if args.suite in ("c2core8", "c2eval12", "c3followup2") or config.get("pretokenize",False):
                tokenization = {}
                token_ids = {}
                for row_index, (row_id, task) in enumerate(task_rows):
                    task_policy = per_task_request_policy(config, row_id)
                    if dynamic_history and row_index:
                        continue  # later turns depend on actual previous API answers
                    messages = task.get("messages") or [{"role":"user","content":task["prompt"]}]
                    kwargs = task_template_kwargs(task)
                    template = fetch("/apply-template",{"model":model_id,
                                      "messages":messages,
                                      "max_tokens":task_policy["max_tokens"],
                                      "temperature":0,"seed":42, **kwargs})
                    if type(template.get("prompt")) is not str:
                        raise GateError(f"official template unavailable for {row_id}")
                    tokenized = fetch("/tokenize",{"content":template["prompt"],
                                       "add_special":False,"parse_special":True})
                    ids = tokenized.get("tokens")
                    if type(ids) is not list or any(type(x) is not int for x in ids) or \
                       not 0 < len(ids) <= config.get("n_ctx",4096)-task_policy["max_tokens"]:
                        raise GateError(f"official tokenization exceeds output reserve for {row_id}")
                    bounds = config.get("prompt_token_ranges",{}).get(row_id)
                    if bounds and not bounds[0] <= len(ids) <= bounds[1]:
                        raise GateError(f"official tokenization outside frozen range for {row_id}")
                    expected_ids = config.get("expected_official_token_ids", {}).get(row_id)
                    if expected_ids is not None and ids != expected_ids:
                        raise GateError("official rendered IDs differ from frozen fixture")
                    tokenization[row_id] = {"count":len(ids),"token_ids_sha256":digest(ids)}
                    token_ids[row_id] = ids
                if config.get("freeze_token_ids",False) and not dynamic_history:
                    with open(paths[".tokenization.json"],"x") as out:
                        json.dump(token_ids,out,indent=2,allow_nan=False);out.write("\n")
                validate_token_relationships(token_ids,
                                             config.get('token_id_relationships', []))
                preflight["prompt_tokenization"] = tokenization
            previous_assistant = None
            history_messages = None
            first_assistant_content = None
            for row_index, (row_id, task) in enumerate(task_rows):
                task_policy = per_task_request_policy(config, row_id)
                if idle_schedule[row_index]:
                    until = time.monotonic() + idle_schedule[row_index]
                    while time.monotonic() < until:
                        if reasons or server.poll() is not None:
                            raise GateError('server/watchdog stopped during session idle')
                        stop.wait(max(0, min(1, until - time.monotonic())))
                if reasons or server.poll() is not None: raise GateError("server/watchdog stopped")
                messages = task.get("messages") or [{"role":"user","content":task["prompt"]}]
                if dynamic_history and row_index:
                    messages = assistant_history_messages(
                        history_messages, previous_assistant, messages)
                    template = fetch('/apply-template', {'model':model_id,
                                     'messages':messages,
                                     'max_tokens':task_policy['max_tokens'],
                                     'temperature':0,'seed':42,
                                     **task_template_kwargs(task)})
                    if type(template.get('prompt')) is not str:
                        raise GateError('dynamic official template unavailable')
                    ids = fetch('/tokenize', {'content':template['prompt'],
                                'add_special':False,'parse_special':True}).get('tokens')
                    if type(ids) is not list or any(type(x) is not int for x in ids) or \
                       not 0 < len(ids) <= config.get('n_ctx',4096)-task_policy['max_tokens']:
                        raise GateError('dynamic official tokenization exceeds reserve')
                    bounds = config.get('prompt_token_ranges',{}).get(row_id)
                    if bounds and not bounds[0] <= len(ids) <= bounds[1]:
                        raise GateError('dynamic official tokenization outside frozen range')
                    tokenization[row_id] = {'count':len(ids),'token_ids_sha256':digest(ids)}
                    token_ids[row_id] = ids
                stream_requests = config.get('stream_requests', False)
                payload = {"model":model_id,"messages":messages,
                           "max_tokens":task_policy["max_tokens"],
                           "temperature":0,"seed":42,"stream":stream_requests,
                           **task_template_kwargs(task)}
                if stream_requests:
                    payload['stream_options'] = {'include_usage': True}
                if "cache_prompt" in task:
                    payload["cache_prompt"] = task["cache_prompt"]
                if row_id == trace_trigger_id:
                    trigger_mono_ns = time.monotonic_ns()
                    with paths['.trace-trigger.json'].open('x') as trigger_out:
                        json.dump({'schema':'c122-trace-trigger-v1',
                                   'run_id':args.run_id,'request_id':row_id,
                                   'mono_ns':trigger_mono_ns,
                                   'utc':dt.datetime.now(dt.timezone.utc).isoformat()},
                                  trigger_out,allow_nan=False)
                        trigger_out.write('\n')
                        trigger_out.flush(); os.fsync(trigger_out.fileno())
                if request_markers:
                    request_started_ns = time.monotonic_ns()
                    request_started = request_started_ns / 1e9
                    marker_file.write(json.dumps({'schema':'c85-request-monotonic-v1',
                        'run_id':args.run_id,'request_id':row_id,'kind':'REQUEST_START',
                        'mono_ns':request_started_ns},allow_nan=False)+'\n')
                    marker_file.flush(); os.fsync(marker_file.fileno())
                else:
                    request_started = time.monotonic()
                start = request_started-t0
                if protocol.get('c18'):
                    c18_request_active.set()
                stream_metrics = None
                request_timeout = task_policy["per_request_timeout_s"]
                if type(request_timeout) not in (int,float) or not math.isfinite(request_timeout) or request_timeout <= 0:
                    raise GateError("invalid per-request wall timeout")
                evidence = Evidence(Path(str(stem)+f'.request-{row_index+1}.jsonl'),
                                    row_id, request_started, request_timeout)
                _REQUEST_LOCAL.evidence = evidence
                def cancel_request():
                    reasons.append('PER_REQUEST_WALL_TIMEOUT')
                    stop_server()
                request_watchdog = Deadline(request_started + request_timeout,
                                            cancel_request)
                request_watchdog.start()
                if stream_requests:
                    response, stream_metrics = stream_chat(
                        payload, task_policy['per_request_timeout_s'],
                        request_started)
                else:
                    response = fetch("/v1/chat/completions",payload,
                                     timeout=task_policy["per_request_timeout_s"])
                request_completed = time.monotonic()
                within_deadline = request_watchdog.complete(request_completed)
                evidence.write('RESPONSE_COMPLETE', response=response,
                               stream_metrics=stream_metrics,
                               completed_monotonic=request_completed,
                               accepted=False, validation_pending=True)
                choices = response.get('choices') if type(response) is dict else None
                choice = choices[0] if type(choices) is list and len(choices) == 1 and type(choices[0]) is dict else {}
                current_item = {"id":row_id,"source_task_id":task["id"],"category":task["category"],
                    "started_s":start,"ended_s":request_completed-t0,
                    "finish_reason":choice.get('finish_reason'),
                    "usage":response.get('usage') if type(response) is dict else None,
                    "timings":response.get('timings') if type(response) is dict else None,
                    "message":choice.get('message'), "raw_response":response,
                    "accepted":False, "invalid_reason":"VALIDATION_PENDING",
                    "deadline_monotonic":request_started+request_timeout,
                    "completed_monotonic":request_completed}
                if stream_metrics is not None:
                    current_item['stream_metrics'] = stream_metrics
                raw.append(current_item)
                if not within_deadline:
                    current_item['invalid_reason'] = 'PER_REQUEST_WALL_TIMEOUT'
                    raise GateError("PER_REQUEST_WALL_TIMEOUT")
                if request_markers:
                    request_ended_ns = time.monotonic_ns()
                    end = request_ended_ns / 1e9 - t0
                    marker_file.write(json.dumps({'schema':'c85-request-monotonic-v1',
                        'run_id':args.run_id,'request_id':row_id,'kind':'RESPONSE_COMPLETE',
                        'mono_ns':request_ended_ns},allow_nan=False)+'\n')
                    marker_file.flush(); os.fsync(marker_file.fileno())
                else:
                    end = time.monotonic()-t0
                if protocol.get('c18'):
                    c18_request_active.clear()
                choices = response.get("choices")
                if type(choices) is not list or len(choices) != 1 or type(choices[0].get("message")) is not dict:
                    raise GateError(f"missing assistant message for {row_id}")
                validate_expected_message(choices[0]['message'], task)
                if result_validator is not None:
                    current_item['functional_validation'] = result_validator(row_id, current_item)
                if (args.suite in ("c2core8", "c2eval12", "c3followup2") or
                    config.get("pretokenize",False)) and \
                   response.get("usage",{}).get("prompt_tokens") != \
                   tokenization[row_id]["count"]:
                    raise GateError(f"API prompt count differs from preflight tokenizer for {row_id}")
                item = current_item
                if request_markers:
                    item['monotonic_request_markers_ns'] = {
                        'request_start':request_started_ns,
                        'response_complete':request_ended_ns}
                if require_natural:
                    require_natural_completion(
                        item, task_policy['max_tokens'])
                required_pattern = config.get('first_assistant_content_pattern')
                if required_pattern is not None:
                    content = item['message'].get('content')
                    if row_index == 0:
                        if type(content) is not str or re.fullmatch(required_pattern, content) is None:
                            raise GateError('first assistant content outside frozen pattern')
                        first_assistant_content = content
                    elif content != first_assistant_content:
                        raise GateError('assistant-history answer changed')
                dynamic_minimum = config.get('dynamic_cache_min_common')
                if dynamic_minimum is not None:
                    timing = item.get('timings') or {}
                    if row_index == 0:
                        if timing.get('cache_n') != 0:
                            raise GateError('first dynamic request unexpectedly cached')
                    else:
                        validate_generated_prefix_cache(
                            token_ids[task_rows[row_index-1][0]], token_ids[row_id],
                            timing.get('cache_n'), timing.get('prompt_n'),
                            raw[-2]['usage']['completion_tokens'], dynamic_minimum,
                            config.get('dynamic_cache_max_lost',32))
                if dynamic_history:
                    history_messages = messages
                    previous_assistant = choices[0]['message']
                print(json.dumps({"id":row_id,"elapsed_s":end-start,"usage":item["usage"]}),flush=True)
                if minimum is not None:
                    cache_n = item.get('timings',{}).get('cache_n')
                    if row_index == 0:
                        if cache_n != 0:
                            raise GateError('first session request unexpectedly reused cache')
                    else:
                        validate_adjacent_cache(token_ids[task_rows[row_index-1][0]],
                                                token_ids[row_id], cache_n, minimum,
                                                max_lost)
                if reasons:
                    raise GateError('REQUEST_INVALIDATED_BY_MONITOR')
                item['accepted'] = True
                item['invalid_reason'] = None
                evidence.write('REQUEST_TERMINAL', accepted=True,
                               watchdog=request_watchdog.finish())
                evidence.close(); evidence = None; current_item = None
                _REQUEST_LOCAL.evidence = None
        except Exception as exc:
            if current_item is not None:
                current_item['accepted'] = False
                current_item['invalid_reason'] = str(exc)
            if evidence is not None and not evidence.truncated:
                evidence.write('REQUEST_TERMINAL', accepted=False,
                    invalid_reason=str(exc), transport_complete=current_item is not None,
                    watchdog=request_watchdog.finish() if request_watchdog else None)
            reasons.append(f"RUN_ERROR:{type(exc).__name__}:{exc}")
        except KeyboardInterrupt:
            reasons.append('INTERRUPTED_BY_OPERATOR')
        finally:
            # Keep sampling through graceful shutdown; ending the sampler first
            # left an unobserved >2 s process tail in the initial target smoke.
            if request_watchdog is not None:
                watchdog_status = request_watchdog.finish()
                if watchdog_status['cancel_error']:
                    reasons.append('CANCEL_ERROR:'+watchdog_status['cancel_error'])
            if evidence is not None:
                evidence.close()
            _REQUEST_LOCAL.evidence = None
            try:
                stop_server()
            except Exception as exc:
                reasons.append(f'CLEANUP_IDENTITY_OR_TIMEOUT:{exc}')
            stop.set();watcher.join(timeout=5)
            if dynamic_history and token_ids:
                with open(paths['.tokenization.json'],'x') as out:
                    json.dump(token_ids,out,indent=2,allow_nan=False);out.write('\n')
    ended = time.monotonic()-t0
    model_after = model.stat()
    if (model_after.st_dev,model_after.st_ino,model_after.st_size,model_after.st_mtime_ns) != \
       (model_before.st_dev,model_before.st_ino,model_before.st_size,model_before.st_mtime_ns):
        reasons.append("MODEL_IDENTITY_CHANGED")
    cg_end = cgroup_state()
    reasons.extend(server_endpoint_reasons(cg_end, cg_start, resource_contract if prospective else None))
    request_evidence = [{'path':str(p),'bytes':p.stat().st_size,'sha256':sha256(p)}
                        for p in sorted(output_root.glob(args.run_id+'.request-*.jsonl'))]
    result = {"schema_version":"c2-server-raw-v1","preflight":preflight,
              "ended_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"elapsed_s":ended,
              "returncode":server.returncode,"stop_reasons":reasons,"results":raw,
              "cgroup_end":cg_end,"sample_count":len(samples),
              "launch_identity":launch["process_identity"], "request_evidence":request_evidence,
              "source_sha256":{s:sha256(p) for s,p in paths.items() if s in
                               (".launch.json",".tokenization.json",".stdout",".stderr",".samples.jsonl") and p.exists()}}
    with open(paths[".json"],"x") as out:
        json.dump(result,out,indent=2,allow_nan=False);out.write("\n")
    if not prospective and not reasons and len(raw) == len(task_rows) and server.returncode == 0:
        try:
            doc = normalize(raw,protocol,config,samples,paths[".stderr"].read_text(errors="replace"),
                            ended,server.returncode,reasons)
            with open(paths[".normalized.json"],"x") as out:
                json.dump(doc,out,indent=2,allow_nan=False);out.write("\n")
        except Exception as exc:
            reasons.append(f"NORMALIZATION_ERROR:{type(exc).__name__}:{exc}")
    print(json.dumps({"run_id":args.run_id,"completed":len(raw),"elapsed_s":ended,
                      "stop_reasons":reasons,"normalized":paths[".normalized.json"].exists()}),flush=True)
    return 0 if not reasons and len(raw)==len(task_rows) and server.returncode==0 and \
           (prospective or paths[".normalized.json"].exists()) else 1


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
