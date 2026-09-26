#!/usr/bin/env python3
"""Run the fixed public task suite against one bounded localhost llama-server."""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from run_bounded import (backend_library_hashes, cgroup_state, gpu_state,
                         mem_available, model_fd_state, proc_status, sha256,
                         thermal_state)


ROOT = Path(__file__).resolve().parents[1]
PORT = 18367
MODELS = {
    "stock20b": {
        "path": Path("/home/pmglo/.local/share/tesy/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf"),
        "sha256_verified": "52f57ab7d3df3ba9173827c1c6832e73375553a846f3e32b49f1ae2daad688d4",
        "revision": "a7443ebb00ba299cbbbf7e9b69487670447ae8c0",
        "backend": "stock", "gpu_layers": 14,
    },
    "target120b": {
        "path": Path("/home/pmglo/models/gpt-oss-120b-gguf/gpt-oss-120b-MXFP4.gguf"),
        "sha256_verified": "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d",
        "revision": "238abdd290bb874b90a5da1b4549881b7d05c091",
        "backend": "streaming", "gpu_layers": 8,
    },
}


def fetch(path, payload=None, timeout=10):
    body = None if payload is None else json.dumps(payload).encode()
    req = Request(f"http://127.0.0.1:{PORT}{path}", data=body,
                  headers={"Content-Type": "application/json"} if body else {},
                  method="POST" if body else "GET")
    with urlopen(req, timeout=timeout) as response:
        return json.load(response)


def first_text_latency(model_id):
    payload = {"model": model_id, "messages": [{"role": "user", "content":
               "What is 7 plus 5? Give the number."}], "max_tokens": 128,
               "temperature": 0, "seed": 42, "stream": True}
    req = Request(f"http://127.0.0.1:{PORT}/v1/chat/completions",
                  data=json.dumps(payload).encode(),
                  headers={"Content-Type": "application/json"}, method="POST")
    start = time.monotonic()
    first = None
    first_reasoning = None
    first_final = None
    text_chunks = 0
    with urlopen(req, timeout=360) as response:
        for raw in response:
            line = raw.decode(errors="replace").strip()
            if line == "data: [DONE]":
                break
            if not line.startswith("data: "):
                continue
            event = json.loads(line[6:])
            for choice in event.get("choices", []):
                delta = choice.get("delta") or {}
                if delta.get("content") or delta.get("reasoning_content"):
                    text_chunks += 1
                    if first is None:
                        first = time.monotonic() - start
                    if delta.get("reasoning_content") and first_reasoning is None:
                        first_reasoning = time.monotonic() - start
                    if delta.get("content") and first_final is None:
                        first_final = time.monotonic() - start
    return {"first_text_chunk_s": round(first, 3) if first is not None else None,
            "first_reasoning_chunk_s": round(first_reasoning, 3) if first_reasoning is not None else None,
            "first_final_chunk_s": round(first_final, 3) if first_final is not None else None,
            "stream_elapsed_s": round(time.monotonic() - start, 3),
            "text_chunk_count": text_chunks,
            "interpretation": "client first received text; chunks are not token intervals"}


def stop_own_server(server):
    if server.poll() is not None:
        return
    os.killpg(server.pid, signal.SIGTERM)
    try:
        server.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(server.pid, signal.SIGKILL)
        server.wait()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--model", choices=MODELS, required=True)
    p.add_argument("--split", choices=("tune", "eval"), default="eval")
    a = p.parse_args()
    if not a.run_id.replace("-", "").replace("_", "").isalnum():
        p.error("invalid run ID")
    spec = MODELS[a.model]
    model = spec["path"]
    if not model.is_file():
        p.error(f"model missing: {model}")
    workload = ROOT / "workloads/task_eval.jsonl"
    tasks = [json.loads(line) for line in workload.read_text().splitlines()]
    tasks = [task for task in tasks if task["split"] == a.split]
    out = ROOT / "results"
    stem = out / a.run_id
    for suffix in (".json", ".stdout", ".stderr", ".samples.jsonl"):
        if Path(str(stem) + suffix).exists():
            p.error(f"run ID exists: {a.run_id}")
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", PORT))
        except OSError as exc:
            p.error(f"localhost port in use: {exc}")
    backend = ROOT / "backends" / spec["backend"]
    binary = backend / "build-gcc15/bin/llama-server"
    command = [str(binary), "-m", str(model), "--host", "127.0.0.1",
               "--port", str(PORT), "-ngl", str(spec["gpu_layers"]),
               "-c", "4096", "-np", "1", "-b", "256", "-ub", "32",
               "-t", "8", "-tb", "8", "--no-warmup", "--no-cache-prompt",
               "--reasoning-effort", "medium", "-lv", "3"]
    if a.model == "stock20b":
        command += ["--load-mode", "dio", "--lazy-mode", "off"]
    else:
        command += ["--no-repack", "--no-op-offload", "--direct-io",
                    "--moe-stream-cache", "24s", "--moe-stream-io-threads", "4",
                    "--moe-stream-direct"]
    env = os.environ.copy()
    explicit_env = {}
    if a.model == "target120b":
        env["LLAMA_MOE_STREAM_NO_PRELOAD"] = "1"
        explicit_env["LLAMA_MOE_STREAM_NO_PRELOAD"] = "1"
    cg_start = cgroup_state()
    if not cg_start or cg_start["memory_max"] != 18 * 2**30 or cg_start["swap_max"] != 0:
        p.error("18 GiB cgroup with zero swap is not enforced")
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    t0 = time.monotonic()
    manifest = {
        "run_id": a.run_id, "started_utc": started, "model": a.model,
        "artifact": str(model), "artifact_revision": spec["revision"],
        "artifact_sha256_previously_verified": spec["sha256_verified"],
        "artifact_size_bytes": model.stat().st_size,
        "backend": spec["backend"],
        "backend_sha": subprocess.check_output(["git", "-C", str(backend),
                                                  "rev-parse", "HEAD"], text=True).strip(),
        "binary_sha256": sha256(binary),
        "backend_libraries_sha256": backend_library_hashes(str(binary), backend),
        "server_command": command, "explicit_env": explicit_env,
        "workload": str(workload.relative_to(ROOT)), "workload_sha256": sha256(workload),
        "split": a.split, "task_ids": [task["id"] for task in tasks],
        "request_policy": {"temperature": 0, "seed": 42, "max_tokens": 512,
                           "reasoning_effort": "medium", "attempts": 1,
                           "prompt_cache": False, "per_request_timeout_s": 360},
        "cgroup_start": cg_start,
        "limits": {"memory_max_bytes": 18 * 2**30, "swap_max_bytes": 0,
                   "rss_gib": 17, "gpu_used_mib": 7000,
                   "min_mem_available_gib": 6, "total_timeout_s": 3600},
        "samples_path": str(stem) + ".samples.jsonl",
        "publication": "local only; stdout/stderr/samples untracked",
        "results": [],
    }
    stop = threading.Event()
    reasons = []
    maxima = {"rss_bytes": 0, "cgroup_memory_bytes": 0, "swap_bytes": 0,
              "gpu_used_mib": 0, "gpu_temperature_c": 0,
              "cpu_tctl_c": 0, "nvme_composite_c": 0}
    last_sample = {}
    with open(str(stem) + ".stdout", "wb") as stdout, \
         open(str(stem) + ".stderr", "wb") as stderr, \
         open(str(stem) + ".samples.jsonl", "w") as samples:
        server = subprocess.Popen(command, stdout=stdout, stderr=stderr,
                                  env=env, start_new_session=True)

        def monitor():
            nonlocal last_sample
            try:
                while not stop.is_set() and server.poll() is None:
                    ps = proc_status(server.pid)
                    cg = cgroup_state()
                    gpu = gpu_state()
                    thermal = thermal_state()
                    available = mem_available()
                    fds = model_fd_state(server.pid, str(model))
                    now = round(time.monotonic() - t0, 3)
                    sample = {"elapsed_s": now, "proc": ps, "cgroup": cg,
                              "gpu": gpu, "thermal": thermal,
                              "mem_available_bytes": available, "model_fds": fds}
                    samples.write(json.dumps(sample) + "\n")
                    samples.flush()
                    last_sample = sample
                    maxima["rss_bytes"] = max(maxima["rss_bytes"], ps.get("VmRSS", 0))
                    maxima["swap_bytes"] = max(maxima["swap_bytes"], ps.get("VmSwap", 0))
                    if cg:
                        maxima["cgroup_memory_bytes"] = max(maxima["cgroup_memory_bytes"], cg["memory_current"] or 0)
                    if gpu:
                        maxima["gpu_used_mib"] = max(maxima["gpu_used_mib"], gpu["used_mib"])
                        maxima["gpu_temperature_c"] = max(maxima["gpu_temperature_c"], gpu["temperature_c"])
                    if thermal:
                        for key in ("cpu_tctl_c", "nvme_composite_c"):
                            maxima[key] = max(maxima[key], thermal.get(key, 0))
                    reason = None
                    if now > 3600:
                        reason = "TIMEOUT"
                    elif ps.get("VmSwap", 0) or (cg and cg["swap_current"]):
                        reason = "SWAP_USED"
                    elif cg and cg["events"].get("oom", 0) > cg_start["events"].get("oom", 0):
                        reason = "CGROUP_OOM"
                    elif cg and cg["events"].get("max", 0) > cg_start["events"].get("max", 0):
                        reason = "CGROUP_LIMIT_HIT"
                    elif ps.get("VmRSS", 0) > 17 * 2**30:
                        reason = "RSS_GUARD"
                    elif available is not None and available < 6 * 2**30:
                        reason = "HOST_HEADROOM_GUARD"
                    elif gpu and gpu["used_mib"] > 7000:
                        reason = "GPU_GUARD"
                    if reason:
                        reasons.append(reason)
                        stop_own_server(server)
                        break
                    stop.wait(1)
            except Exception as exc:
                reasons.append(f"MONITOR_ERROR: {type(exc).__name__}: {exc}")
                stop_own_server(server)

        watcher = threading.Thread(target=monitor, daemon=True)
        watcher.start()
        try:
            ready = False
            while time.monotonic() - t0 < 90 and not reasons:
                if server.poll() is not None:
                    raise RuntimeError(f"server exited during load: {server.returncode}")
                try:
                    ready = fetch("/health", timeout=3).get("status") == "ok"
                except (HTTPError, URLError, OSError, ValueError):
                    pass
                if ready:
                    break
                time.sleep(0.5)
            if not ready:
                raise TimeoutError("server readiness exceeded 90 seconds")
            manifest["ready_elapsed_s"] = round(time.monotonic() - t0, 3)
            model_id = fetch("/v1/models")["data"][0]["id"]
            manifest["server_model_id"] = model_id
            manifest["first_text_smoke"] = first_text_latency(model_id)
            for task in tasks:
                if reasons or server.poll() is not None:
                    raise RuntimeError("server or watchdog stopped before task")
                payload = {"model": model_id,
                           "messages": [{"role": "user", "content": task["prompt"]}],
                           "max_tokens": 512, "temperature": 0, "seed": 42,
                           "stream": False}
                begin = time.monotonic()
                response = fetch("/v1/chat/completions", payload, timeout=360)
                elapsed = round(time.monotonic() - begin, 3)
                choices = response.get("choices") or []
                if len(choices) != 1 or not isinstance(choices[0].get("message"), dict):
                    raise RuntimeError(f"missing assistant answer for {task['id']}")
                manifest["results"].append({"task_id": task["id"],
                    "category": task["category"], "elapsed_s": elapsed,
                    "finish_reason": choices[0].get("finish_reason"),
                    "usage": response.get("usage"),
                    "timings": response.get("timings"),
                    "message": choices[0]["message"]})
                print(json.dumps({"task_id": task["id"], "elapsed_s": elapsed,
                                  "finish_reason": choices[0].get("finish_reason"),
                                  "usage": response.get("usage")}), flush=True)
        except Exception as exc:
            reasons.append(f"RUN_ERROR: {type(exc).__name__}: {exc}")
        finally:
            stop.set()
            stop_own_server(server)
            watcher.join(timeout=5)
    manifest.update({"ended_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                     "elapsed_s": round(time.monotonic() - t0, 3),
                     "stop_reasons": reasons, "returncode": server.returncode,
                     "maxima": maxima, "last_sample": last_sample,
                     "cgroup_end": cgroup_state(),
                     "stdout_path": str(stem) + ".stdout",
                     "stderr_path": str(stem) + ".stderr"})
    Path(str(stem) + ".json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"run_id": a.run_id, "completed_tasks": len(manifest["results"]),
                      "elapsed_s": manifest["elapsed_s"], "stop_reasons": reasons,
                      "maxima": maxima}), flush=True)
    return 0 if not reasons and len(manifest["results"]) == len(tasks) else 1


if __name__ == "__main__":
    sys.exit(main())
