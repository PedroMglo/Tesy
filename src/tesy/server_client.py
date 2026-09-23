from __future__ import annotations

import argparse
import http.client
import json
import math
import time
from pathlib import Path
from urllib.parse import urlsplit


class ServerClientError(RuntimeError):
    pass


def _parse_sse_line(line: bytes) -> dict | None:
    text = line.decode("utf-8", errors="strict").strip()
    if not text or text.startswith(":"):
        return None
    if not text.startswith("data:"):
        return None
    payload = text[5:].strip()
    if payload == "[DONE]":
        return None
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ServerClientError("SSE data must decode to an object")
    return value


def _event_token_ids(event: dict) -> list[int]:
    raw = event.get("tokens")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ServerClientError("SSE tokens field must be a list")
    result: list[int] = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ServerClientError("SSE token IDs must be integers")
        result.append(value)
    return result


def run_completion(
    url: str,
    prompt: str,
    n_predict: int,
    timeout_s: float,
) -> dict:
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ServerClientError("only loopback http server URLs are admitted")
    port = parsed.port or 80
    path = parsed.path or "/completion"

    body = json.dumps(
        {
            "prompt": prompt,
            "n_predict": n_predict,
            "stream": True,
            "cache_prompt": False,
            "temperature": 0.0,
            "top_k": 1,
            "seed": 42,
            "timings_per_token": True,
            "return_progress": True,
            "return_tokens": True,
        },
        separators=(",", ":"),
    )

    conn = http.client.HTTPConnection(parsed.hostname, port, timeout=timeout_s)
    t0 = time.perf_counter_ns()
    conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
    response = conn.getresponse()
    if response.status != 200:
        data = response.read().decode("utf-8", errors="replace")
        raise ServerClientError(f"server returned HTTP {response.status}: {data}")

    first_content_ns: int | None = None
    final: dict | None = None
    chunks = 0
    generated_token_ids: list[int] = []
    for raw in response:
        event = _parse_sse_line(raw)
        if event is None:
            continue
        generated_token_ids.extend(_event_token_ids(event))
        content = event.get("content")
        if first_content_ns is None and isinstance(content, str) and content:
            first_content_ns = time.perf_counter_ns()
        chunks += 1
        if event.get("stop") is True or "timings" in event:
            final = event

    t1 = time.perf_counter_ns()
    conn.close()

    if first_content_ns is None:
        raise ServerClientError("stream produced no non-empty content")
    if final is None or not isinstance(final.get("timings"), dict):
        raise ServerClientError("stream ended without final timings")

    timings = final["timings"]
    required = [
        "prompt_n",
        "prompt_ms",
        "prompt_per_second",
        "predicted_n",
        "predicted_ms",
        "predicted_per_second",
    ]
    for key in required:
        value = timings.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ServerClientError(f"missing/non-numeric timing {key}")
        if not math.isfinite(float(value)) or float(value) < 0:
            raise ServerClientError(f"invalid timing {key}: {value}")

    predicted_n = timings["predicted_n"]
    if (
        isinstance(predicted_n, bool)
        or not isinstance(predicted_n, int)
        or predicted_n < 0
    ):
        raise ServerClientError("predicted_n must be a non-negative integer")
    if len(generated_token_ids) != predicted_n:
        raise ServerClientError(
            "streamed token count does not match server predicted_n: "
            f"{len(generated_token_ids)} != {predicted_n}"
        )

    return {
        "schema": "tesy.stock_server_request.v1",
        "classification": "MEASURED_REQUEST_TIMING_DIAGNOSTIC",
        "ttft_ms": (first_content_ns - t0) / 1e6,
        "request_wall_ms": (t1 - t0) / 1e6,
        "sse_json_chunks": chunks,
        "generated_token_ids": generated_token_ids,
        "generated_token_count": len(generated_token_ids),
        "timings": {key: timings[key] for key in required},
        "stop_type": final.get("stop_type"),
        "claim_boundary": (
            "TTFT is client-observed to first non-empty SSE content. Server timings "
            "come from pinned llama-server. This is not physical I/O telemetry."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--n-predict", type=int, default=64)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.output.exists():
        raise SystemExit(f"refusing to replace {args.output}")
    prompt = args.prompt_file.read_text(encoding="utf-8")
    result = run_completion(args.url, prompt, args.n_predict, args.timeout)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
