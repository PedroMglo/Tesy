#!/usr/bin/env python3
"""Bounded localhost chat smoke; always stops the server it starts."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PORT = 18365


def fetch(path, payload=None, timeout=3):
    body = None if payload is None else json.dumps(payload).encode()
    req = Request(f"http://127.0.0.1:{PORT}{path}", data=body,
                  headers={"Content-Type": "application/json"} if body else {},
                  method="POST" if body else "GET")
    with urlopen(req, timeout=timeout) as response:
        return json.load(response)


def main():
    if len(sys.argv) != 3 or not Path(sys.argv[1]).is_file():
        raise SystemExit("usage: server_check.py MODEL.gguf RUN_ID")
    model = str(Path(sys.argv[1]).resolve())
    run_id = sys.argv[2]
    if not run_id.replace("-", "").replace("_", "").isalnum():
        raise SystemExit("invalid RUN_ID")
    binary = ROOT / "backends/streaming/build-gcc15/bin/llama-server"
    command = [str(binary), "-m", model, "--host", "127.0.0.1", "--port", str(PORT),
               "-ngl", "8", "-c", "4096", "-np", "1", "-b", "256", "-ub", "32",
               "-t", "8", "-tb", "8", "--no-warmup", "--no-repack", "--no-op-offload",
               "--direct-io", "--moe-stream-cache", "16s", "--moe-stream-io-threads", "4",
               "--moe-stream-direct"]
    env = __import__("os").environ.copy()
    env["LLAMA_MOE_STREAM_NO_PRELOAD"] = "1"
    start = time.monotonic()
    stdout_path = ROOT / f"results/{run_id}-server.stdout"
    stderr_path = ROOT / f"results/{run_id}-server.stderr"
    summary_path = ROOT / f"results/{run_id}-summary.json"
    if any(p.exists() for p in (stdout_path, stderr_path, summary_path)):
        raise RuntimeError("run output already exists")
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        server = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=env)
        try:
            while time.monotonic() - start < 45:
                if server.poll() is not None:
                    raise RuntimeError(f"server exited before readiness: {server.returncode}")
                try:
                    health = fetch("/health")
                    if health.get("status") == "ok":
                        break
                except (HTTPError, URLError, OSError, ValueError):
                    pass
                time.sleep(0.5)
            else:
                raise TimeoutError("server readiness exceeded 45 seconds")
            model_info = fetch("/v1/models")
            model_id = model_info["data"][0]["id"]
            response = fetch("/v1/chat/completions", {
                "model": model_id,
                "messages": [{"role": "user", "content": "What is 7 plus 5? Give the number."}],
                "max_tokens": 128,
                "temperature": 0,
                "stream": False,
            }, timeout=75)
            choices = response.get("choices", [])
            if not choices:
                raise RuntimeError("chat response has no choices")
            summary = {"run_id": run_id, "server_command": command,
                       "server_env": {"LLAMA_MOE_STREAM_NO_PRELOAD": "1"},
                       "server_binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                       "host": "127.0.0.1", "port": PORT,
                       "elapsed_s": round(time.monotonic() - start, 3),
                       "model_id": model_id, "usage": response.get("usage"),
                       "finish_reason": choices[0].get("finish_reason"),
                       "message": choices[0].get("message")}
            summary_path.write_text(json.dumps(summary, indent=2) + "\n")
            print(json.dumps(summary))
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == "__main__":
    main()
