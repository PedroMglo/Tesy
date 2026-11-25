"""Two natural C281 chat requests against an already monitored READY stock derivative."""

import http.client
import json
import math
import socket
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUAL = HERE.parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(QUAL)]
import optin_integration_client as original  # noqa: E402
from aster_budget.probe import listener_port  # noqa: E402
from c2_gate import strict_json  # noqa: E402
from c2_server_run import parse_chat_stream  # noqa: E402
from nominal_stock_input.screen import AUTHORITIES, DAY, packed_ids, pinned, sha  # noqa: E402
from nvme_conversation.contract import owned_listener  # noqa: E402
from request_evidence import Deadline, Evidence  # noqa: E402

FIXTURE = "c3e0b72ecaa2e13ac6871af6cef5ef05d6ba1b5b7f76cf685177ce83f121b92c"
WORKLOAD = "f4aac5a70e019b7ec272b1ddcd0d7e63c62755b61ff4830a6c5bef29184db33a"
KWARGS = {"reasoning_effort": "medium", "tesy_template_date": DAY}
CAP = 256


class Gate(ValueError):
    """All public reason labels are literals. SSE and response data remain in private raw."""


def check(ok, label):
    if not ok:
        raise Gate(label)


def expected_render(turn, reference, messages):
    if turn == 1:
        check(messages == reference["messages"], "T1_messages")
        return reference["rendered_prompt"]
    ref = reference["messages"]
    check(messages[0] == ref[0] and messages[2] == ref[2], "T2_user_turns")
    fmt = "<|start|>assistant<|channel|>final<|message|>{}<|end|>"
    old = fmt.format(ref[1]["content"])
    check(reference["rendered_prompt"].count(old) == 1, "ambiguous_assistant_history")
    return reference["rendered_prompt"].replace(old, fmt.format(messages[1]["content"]), 1)


def check_input(turn, reference, messages, prompt, ids):
    expected = expected_render(turn, reference, messages)
    check(isinstance(prompt, str) and prompt == expected, "live_render_differs")
    check(0 < len(ids) <= 8192 - CAP, "context_or_token_reserve")
    digest = sha(packed_ids(ids))
    same_prompt = prompt == reference["rendered_prompt"]
    if same_prompt:
        check(ids == reference["official_ids"], "official_ids_changed_for_same_render")
    return {
        "input_n": len(ids),
        "official_ids_i32le_sha256": digest,
        "render_sha256": sha(prompt.encode()),
        "same_render_as_R0": same_prompt,
        "same_ids_as_R0": ids == reference["official_ids"],
    }


def evaluate(row, turn, ids, previous, response, metrics, first):
    usage, timings = response["usage"], response["timings"]
    choice = response["choices"][0]
    item = {"finish_reason": choice["finish_reason"], "usage": usage, "id": turn}
    row.update(finish_reason="stop" if choice["finish_reason"] == "stop" else "other")
    original.natural_completion(item, CAP, allow_exact_cap=True)
    complete = usage["completion_tokens"]
    cache, prompt, pred = (timings[k] for k in ("cache_n", "prompt_n", "predicted_n"))
    check(
        all(
            type(v) is int and v >= 0
            for v in (cache, prompt, pred, complete, usage["prompt_tokens"], usage["total_tokens"])
        )
        and pred == complete
        and prompt > 0
        and usage["prompt_tokens"] == len(ids)
        and cache + prompt == len(ids)
        and usage["total_tokens"] == len(ids) + complete,
        "prompt_or_generation_accounting",
    )
    check(
        type(usage["prompt_tokens_details"]["cached_tokens"]) is int
        and usage["prompt_tokens_details"]["cached_tokens"] == cache,
        "usage_cache_inconsistent",
    )
    times = (timings["prompt_ms"], timings["predicted_ms"], timings["predicted_per_second"])
    check(
        all(type(v) in (int, float) and math.isfinite(v) and v > 0 for v in times), "phase_clocks"
    )
    row.update(
        completion_n=complete,
        predicted_n=pred,
        cache_n=cache,
        prompt_n=prompt,
        prefill_s=times[0] / 1000,
        decode_s=times[1] / 1000,
        decode_tok_s=times[2],
        tpot_s=times[1] / (1000 * pred),
        first_text_s=metrics["first_text_chunk_s"],
        first_reasoning_s=metrics["first_reasoning_chunk_s"],
        first_final_s=metrics["first_final_content_chunk_s"],
        sse_events=metrics["sse_event_count"],
        content_gate="PASS"
        if original.grade(turn - 1, choice["message"]["content"], first)
        else "FAIL",
    )
    check(row["content_gate"] == "PASS", "content_gate_failed")
    check(
        metrics["done_observed"]
        and row["first_text_s"] is not None
        and 0 <= row["first_text_s"] <= row["first_final_s"] <= row["transport_complete_s"],
        "completion_clocks",
    )
    if turn == 1:
        check(cache == 0, "unexpected_T1_cache")
    else:
        before, previous_count = previous
        row["prompt_ids_common_prefix"] = original.validate_generated_prefix_cache(
            before, ids, cache, prompt, previous_count, 1900, 32
        )
        nominal = (
            row["same_render_as_R0"] and row["same_ids_as_R0"] and (cache, prompt) == (2044, 153)
        )
        row.update(
            paired_nominal_input="MATCHED_IDS_AND_SPLIT" if nominal else "INCONCLUSIVE",
            nominal_first_final_le_10s=row["first_final_s"] <= 10 if nominal else None,
            nominal_decode_ge_6=row["decode_tok_s"] >= 6 if nominal else None,
        )
    row["prefix_gate"] = "PASS"
    return choice["message"]


def exchange(pid, port, cancelled, progress, raw, turn, payload, timeout, row):
    owned_listener(pid, port)
    check(not cancelled.is_set(), "monitor_cancelled")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    body = json.dumps(payload, allow_nan=False).encode()
    with (raw / f"T{turn}-payload.json").open("xb") as f:
        f.write(body)
    row["request_sha256"] = sha(body)
    state = progress["product_progress"]
    start = time.monotonic()
    evidence = Evidence(raw / f"T{turn}-request.jsonl", f"T{turn}", start, timeout)
    state.update(
        phase="chat",
        send_monotonic_s=start,
        deadline_monotonic_s=start + timeout,
        first_final_s=None,
    )
    captured_socket = []

    def abort():
        if captured_socket:
            try:
                captured_socket[0].shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    wd = Deadline(start + timeout, abort)
    wd.start()
    last_native = None
    stamp = start
    try:
        conn.connect()
        captured_socket.append(conn.sock)
        check(
            not cancelled.is_set() and time.monotonic() < start + timeout, "cancelled_before_POST"
        )
        progress["http_requests_sent"] += 1
        progress["sampling_tokens_requested"] += CAP
        conn.request("POST", "/v1/chat/completions", body, {"Content-Type": "application/json"})
        res = conn.getresponse()
        evidence.write("HTTP", status=res.status)
        check(
            res.status == 200 and "text/event-stream" in res.getheader("Content-Type", ""),
            "chat_http_or_media_type",
        )

        def lines():
            nonlocal stamp, last_native
            while True:
                line = res.readline(256 * 1024 + 1)
                stamp = time.monotonic()
                check(stamp < start + timeout, "PER_REQUEST_WALL_TIMEOUT")
                check(not cancelled.is_set(), "monitor_cancelled")
                if not line:
                    return
                check(len(line) <= 256 * 1024, "oversized_SSE_line")
                text = line.decode("utf-8")
                evidence.write("SSE_FRAGMENT", fragment=text, received_monotonic=stamp)
                if text.startswith("data: ") and text[6:].strip() != "[DONE]":
                    obj = strict_json(text[6:])
                    if isinstance(obj.get("__verbose"), dict):
                        last_native = obj["__verbose"].get("tokens")
                    for ch in obj["choices"]:
                        delta = ch.get("delta", {})
                        elapsed = stamp - start
                        if delta.get("role") == "assistant" and "prompt_progress" not in obj:
                            row.setdefault("assistant_role_chunk_s", elapsed)
                        if (
                            isinstance(delta.get("content"), str)
                            and delta["content"].strip()
                            and state["first_final_s"] is None
                        ):
                            state["first_final_s"] = elapsed
                yield line

        result, metrics = parse_chat_stream(lines(), lambda: stamp - start)
        end = time.monotonic()
        row["transport_complete_s"] = end - start
        original.save(raw / f"T{turn}-response.json", result)
        check(wd.complete(end), "PER_REQUEST_WALL_TIMEOUT")
        ids, authority = original.native_output_ids(last_native)
        row["output_ids_authority"] = authority
        if ids is not None:
            row["exposed_output_ids_n"] = len(ids)
            row["exposed_output_ids_sha256"] = sha(packed_ids(ids))
        return result, metrics
    finally:
        conn.close()
        row["watchdog"] = wd.finish()
        row["observed_wall_s"] = time.monotonic() - start
        evidence.close()


class Probe:
    run_id = "stock-nominal-e20-c281"
    pass_status = "PASS_STOCK_TWO_NATURAL_REQUESTS_LOCAL_HISTORY"
    ram_profile = "R0_E20"
    timeout_s = 300
    protocol_path = HERE / "protocol.md"

    def __init__(self, history):
        fixture = json.loads(
            pinned(QUAL / "nominal_stock_input/evidence-r01/receipt.json", FIXTURE)
        )
        check(
            fixture["status"] == "PASS_TWO_NOMINAL_INPUTS_RENDER_AND_OFFICIAL_IDS",
            "nominal_input_fixture",
        )
        rfile, rsha = AUTHORITIES["r0"]
        evidence = json.loads(pinned(QUAL / rfile, rsha))
        check(evidence["status"] == "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY", "R0_evidence")
        self.tasks = json.loads(
            pinned(ROOT / "results/c281-persistent-r0-runtime-20261005/protocol.json", WORKLOAD)
        )["tasks"]
        self.references = []
        for i, (task, f) in enumerate(zip(self.tasks, fixture["turns"], strict=True), 1):
            name = f"T{i}-input.json"
            meta = evidence["local_manifest"]["raw/" + name]
            ref = json.loads(pinned(history / name, meta["sha256"], meta["bytes"]))
            check(
                ref["template_kwargs"] == KWARGS
                and ref["messages"][-1:] == task["messages"]
                and f["historical_input_sha256"] == meta["sha256"]
                and sha(packed_ids(ref["official_ids"])) == f["expected_ids_i32le_sha256"]
                and sha(ref["rendered_prompt"].encode()) == f["expected_render_sha256"],
                "historical_turn_binding",
            )
            self.references.append(ref)

    def run(self, pid, raw, cancelled, progress):
        state = {"phase": "model_id", "completed_turns": 0, "rows": [], "turn": 1}
        progress["product_progress"] = state
        port = listener_port(raw)
        endpoint = f"http://127.0.0.1:{port}"

        def fetch(path, data=None):
            check(not cancelled.is_set(), "monitor_cancelled")
            owned_listener(pid, port)
            return original.fetch(path, data, timeout=4, base_url=endpoint)

        try:
            models = fetch("/v1/models")["data"]
            check(
                len(models) == 1 and isinstance(models[0]["id"], str) and models[0]["id"],
                "server_model_id",
            )
            model = models[0]["id"]
            previous = first = answer = None
            for turn, (ref, task) in enumerate(zip(self.references, self.tasks, strict=True), 1):
                state.update(
                    phase="render",
                    turn=turn,
                    first_final_s=None,
                    send_monotonic_s=None,
                    deadline_monotonic_s=None,
                )
                row = {"turn": turn, "accepted": False}
                state["rows"].append(row)
                messages = (
                    task["messages"]
                    if turn == 1
                    else original.assistant_history_messages(
                        self.tasks[0]["messages"], answer, task["messages"]
                    )
                )
                params = {"model": model, "messages": messages, "chat_template_kwargs": KWARGS}
                prompt = fetch("/apply-template", params)["prompt"]
                state["phase"] = "tokenize"
                ids = fetch(
                    "/tokenize", {"content": prompt, "add_special": False, "parse_special": True}
                )["tokens"]
                original.save(
                    raw / f"T{turn}-input.json",
                    {
                        "messages": messages,
                        "template_kwargs": KWARGS,
                        "rendered_prompt": prompt,
                        "official_ids": ids,
                    },
                )
                row.update(check_input(turn, ref, messages, prompt, ids))
                body = params | {
                    "max_tokens": CAP,
                    "temperature": 0,
                    "seed": 42,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                    "cache_prompt": True,
                    "return_tokens": True,
                    "verbose": True,
                }
                response, metrics = exchange(
                    pid, port, cancelled, progress, raw, turn, body, task["timeout_s"], row
                )
                state["phase"] = "validate"
                check(not cancelled.is_set(), "monitor_cancelled")
                answer = evaluate(row, turn, ids, previous, response, metrics, first)
                row["validated_terminal_s"] = time.monotonic() - state["send_monotonic_s"]
                check(row["validated_terminal_s"] < task["timeout_s"], "PER_REQUEST_WALL_TIMEOUT")
                row["accepted"] = True
                state.update(phase="turn_done", completed_turns=turn, deadline_monotonic_s=None)
                original.save(raw / f"T{turn}-accepted.json", row)
                previous = (ids, row["completion_n"])
                if turn == 1:
                    first = answer["content"]
            state["phase"] = "complete"
            return {
                "rows": state["rows"],
                "completed_turns": state["completed_turns"],
                "nominal_input_fixture_sha256": FIXTURE,
                "workload_sha256": WORKLOAD,
                "r0_evidence_sha256": AUTHORITIES["r0"][1],
            }
        except Exception as e:
            label = str(e) if isinstance(e, Gate) else type(e).__name__
            now = time.monotonic()
            if state.get("deadline_monotonic_s") and now >= state["deadline_monotonic_s"]:
                label = "PER_REQUEST_WALL_TIMEOUT"
            state["failure"] = label
            if state.get("send_monotonic_s") is not None:
                state["elapsed_to_failure_s"] = now - state["send_monotonic_s"]
            original.save(raw / "product-failure.json", state)
            raise Gate(label) from None
