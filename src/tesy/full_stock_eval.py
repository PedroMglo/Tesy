"""One-process stock chat evaluation client; no Tesy candidate is involved."""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.request
from pathlib import Path


def _post_json(url: str, payload: dict, *, timeout: int = 300):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return urllib.request.urlopen(req, timeout=timeout)


def parse_chat_stream(lines: list[bytes]) -> tuple[str, dict, dict, str]:
    """Reject incomplete SSE, missing usage/timings, or non-finite timing data."""
    content: list[str] = []
    usage = None
    timings = None
    finish_reason = None
    done = False
    for raw in lines:
        line = raw.decode("utf-8").strip()
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            done = True
            continue
        event = json.loads(payload)
        if "error" in event:
            raise ValueError(f"server error: {event['error']}")
        for choice in event.get("choices", []):
            delta = choice.get("delta", {})
            if isinstance(delta.get("content"), str):
                content.append(delta["content"])
            if choice.get("finish_reason") is not None:
                finish_reason = choice["finish_reason"]
        if event.get("usage") is not None:
            usage = event["usage"]
        if event.get("timings") is not None:
            timings = event["timings"]
    if not done or usage is None or timings is None or finish_reason is None:
        raise ValueError("incomplete chat stream, usage, timings, or finish reason")
    for key in ("prompt_tokens", "completion_tokens"):
        if not isinstance(usage.get(key), int) or usage[key] < 0:
            raise ValueError(f"invalid usage {key}")
    if usage["completion_tokens"] < 1:
        raise ValueError("no output tokens")
    for key in ("prompt_ms", "predicted_ms", "predicted_per_token_ms"):
        value = timings.get(key)
        if not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"invalid timing {key}")
    if timings.get("predicted_n") != usage["completion_tokens"]:
        raise ValueError("usage and backend timing token counts disagree")
    return "".join(content), usage, timings, finish_reason


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--count-only", action="store_true")
    args = parser.parse_args()

    base = f"http://127.0.0.1:{args.port}"
    start_ns = time.monotonic_ns()
    for _ in range(1200):
        try:
            with urllib.request.urlopen(f"{base}/health", timeout=2) as response:
                health = json.load(response)
            if health.get("status") == "ok":
                break
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass
        time.sleep(0.1)
    else:
        raise RuntimeError("server did not become healthy")
    ready_ns = time.monotonic_ns()

    payload = {
        "messages": [{"role": "user", "content": args.prompt.read_text()}],
        "temperature": 0,
        "top_k": 1,
        "seed": 42,
        "max_tokens": args.max_tokens,
        "cache_prompt": False,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if args.count_only:
        with _post_json(f"{base}/v1/chat/completions/input_tokens", payload) as response:
            count = json.load(response).get("input_tokens")
        if not isinstance(count, int) or count <= 0 or count >= 4096:
            raise ValueError("invalid templated input token count")
        args.output.write_text(json.dumps({
            "schema": "tesy.full_model_stock_chat_prompt_count.v1",
            "prompt_file": str(args.prompt),
            "templated_input_tokens": count,
            "client_health_wait_s": (ready_ns - start_ns) / 1e9,
        }, indent=2, sort_keys=True) + "\n")
        return
    request_ns = time.monotonic_ns()
    lines: list[bytes] = []
    first_content_ns = None
    with _post_json(f"{base}/v1/chat/completions", payload) as response:
        for line in response:
            lines.append(line)
            if first_content_ns is None and line.startswith(b"data: "):
                event_bytes = line[6:].strip()
                if event_bytes != b"[DONE]":
                    event = json.loads(event_bytes)
                    if any(choice.get("delta", {}).get("content") for choice in
                           event.get("choices", [])):
                        first_content_ns = time.monotonic_ns()
    end_ns = time.monotonic_ns()
    content, usage, timings, finish_reason = parse_chat_stream(lines)
    if first_content_ns is None or not content:
        raise ValueError("no visible content/TTFT; preserve failed root")
    result = {
        "schema": "tesy.full_model_stock_chat_run.v1",
        "prompt_file": str(args.prompt),
        "max_tokens": args.max_tokens,
        "client_health_wait_s": (ready_ns - start_ns) / 1e9,
        "ttft_s": (first_content_ns - request_ns) / 1e9,
        "generation_request_s": (end_ns - request_ns) / 1e9,
        "usage": usage,
        "timings": timings,
        "finish_reason": finish_reason,
        "output_text": content,
        "token_ids": None,
        "token_id_limitation": (
            "SSE chat response reports count/text but not the full generated token ID vector."
        ),
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
