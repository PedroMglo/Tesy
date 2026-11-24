"""Prepare the two C133 requests and validate a future independent, private paired capture."""

import argparse
import hashlib
import json
import math
import os
import re
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import c132_diverse_session as session
import c133_diverse_session_retry as historical
from c2_gate import GateError, strict_json
from c2_server_run import assistant_history_messages, digest, require_natural_completion

ROOT = Path(__file__).resolve().parents[2]
IDS = ["c133-turn01", "c133-turn02"]
MODEL = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
DECISION = "9f52ea6f2f09f1be56ab92cc6eac785daca85e51b7cbcaa00a0f134e6160610e"
POLICY = {
    "context": 8192,
    "max_tokens": 768,
    "temperature": 0,
    "seed": 42,
    "date": "2026-09-29",
    "effort": "medium",
    "slots": 1,
}
COUNTS = [(121, 0, 121), (435, 122, 313)]
ROLES = {"r0": "Tesy-R0", "reference": "stock-llama.cpp"}


def require(value):
    if not value:
        raise ValueError("evidence gate")


def read(path, checksum=None):
    # All historical inputs here are small JSON. Read the same bytes that are verified.
    if path.stat().st_size > 256 * 1024**2:
        raise ValueError("oversized private evidence")
    data = path.read_bytes()
    if checksum is not None:
        require(hashlib.sha256(data).hexdigest() == checksum)
    return strict_json(data)


def payload(model, messages):
    return {
        "model": model,
        "messages": messages,
        "max_tokens": POLICY["max_tokens"],
        "temperature": POLICY["temperature"],
        "seed": POLICY["seed"],
        "stream": True,
        "stream_options": {"include_usage": True},
        "cache_prompt": True,
        "chat_template_kwargs": {
            "tesy_template_date": POLICY["date"],
            "reasoning_effort": POLICY["effort"],
        },
    }


def check_response(row, sequence, index, spec):
    require(row["id"] == row["source_task_id"] == IDS[index])
    require_natural_completion(row, POLICY["max_tokens"])
    message = row["message"]
    require(
        message["role"] == "assistant"
        and isinstance(message["content"], str)
        and message["content"].strip()
        and row["stream_metrics"]["done_observed"] is True
    )
    final_s = row["stream_metrics"]["first_final_content_chunk_s"]
    require(type(final_s) in (float, int) and math.isfinite(final_s) and final_s >= 0)
    require(type(sequence) is list and all(type(i) is int and i >= 0 for i in sequence))
    usage, timing = row["usage"], row["timings"]
    sizes = (usage["prompt_tokens"], timing["cache_n"], timing["prompt_n"])
    require(all(type(n) is int and n >= 0 for n in sizes))
    require(sizes[0] == len(sequence) == sizes[1] + sizes[2])
    require(
        type(usage["prompt_tokens_details"]["cached_tokens"]) is int
        and usage["prompt_tokens_details"]["cached_tokens"] == sizes[1]
    )
    require(
        timing["predicted_n"] == usage["completion_tokens"]
        and usage["total_tokens"] == sizes[0] + usage["completion_tokens"]
    )
    return sizes, session.grade(row, spec)["status"] == "PASS"


def prepare(history):
    campaign = ROOT / "results" / historical.ROOT_NAME
    rawdir = history / historical.ROOT_NAME / "raw"
    stem = historical.RUN_ID
    decision = read(campaign / "decision.json", DECISION)
    analysis = read(campaign / "analysis.json", decision["analysis_sha256"])
    raw = read(rawdir / (stem + ".json"), decision["raw_sha256"])
    receipt = read(rawdir / (stem + ".receipt.json"), decision["receipt_sha256"])
    pre = raw["preflight"]
    proto = read(campaign / "protocols" / (stem + ".json"), pre["protocol_sha256"])
    require(proto["identity"]["model_sha256"] == pre["model_sha256_prior_verified"] == MODEL)
    require(
        receipt["model_launch_observed"] is True and receipt["raw_sha256"] == decision["raw_sha256"]
    )
    work = read(historical.WORKLOAD, proto["identity"]["workload_sha256"])
    cfg = pre["config"]
    require(work["template_date"] == POLICY["date"] and cfg["n_ctx"] == POLICY["context"])
    require(
        all(
            cfg["request_policy"][key] == POLICY[key]
            for key in ["seed", "temperature", "max_tokens"]
        )
    )
    require(
        cfg["request_policy"]["reasoning_effort"] == POLICY["effort"]
        and cfg["append_previous_assistant_to_next"] is True
    )
    token_map = read(
        rawdir / (stem + ".tokenization.json"), analysis["official_tokenization_sha256"]
    )
    specs, rows = work["tasks"][:2], raw["results"][:2]
    require([s["id"] for s in specs] == IDS)
    users = [[{"role": "user", "content": s["message"]}] for s in specs]
    historical_second = assistant_history_messages(users[0], rows[0]["message"], users[1])
    messages = [users[0], historical_second]
    turns = []
    for i, (row, spec) in enumerate(zip(rows, specs, strict=True)):
        seq = token_map[IDS[i]]
        counts, grade = check_response(row, seq, i, spec)
        require(counts == COUNTS[i] and grade is (i == 0))
        require(receipt["results"][i]["message_sha256"] == digest(row["message"]))
        turns.append(
            {
                "prompt_tokens": counts[0],
                "cached_tokens": counts[1],
                "new_tokens": counts[2],
                "prompt_ids_sha256": digest(seq),
                "messages_sha256": digest(messages[i]),
                "completion_tokens": row["usage"]["completion_tokens"],
                "historical_content_pass": grade,
            }
        )
    manifest = {
        "schema": "tesy-two-turn-input-v1",
        "policy": POLICY,
        "model_sha256": MODEL,
        "turns": turns,
        "decision_sha256": DECISION,
        "raw_sha256": decision["raw_sha256"],
        "workload_sha256": proto["identity"]["workload_sha256"],
        "receipt_sha256": decision["receipt_sha256"],
        "protocol_sha256": pre["protocol_sha256"],
        "tokenizations_sha256": analysis["official_tokenization_sha256"],
    }
    return manifest, specs, users, historical_second


def arm(root, mode, plan_hash, pinned, inputs):
    manifest, specs, users, fixed_second = inputs
    protocol = read(root / "protocol.json", pinned)
    require(protocol["policy"] == POLICY and protocol["identity"]["model_sha256"] == MODEL)
    identity = protocol["identity"]
    require(
        re.fullmatch(r"[0-9a-f]{64}", identity["binary_sha256"])
        and re.fullmatch(r"[0-9a-f]{40}", identity["backend_tree"])
        and re.fullmatch(r"[0-9a-f]{64}", identity["library_manifest_sha256"])
    )
    rec = read(root / "receipt.json")
    require(
        rec["schema"] == "tesy-two-turn-capture-v1"
        and rec["model_launch_observed"] is True
        and rec["protocol_sha256"] == pinned
        and rec["pair_sha256"] == plan_hash
    )
    require(isinstance(rec["run_id"], str) and rec["run_id"])
    raw = read(root / "raw.json", rec["raw_sha256"])
    requests = read(root / "requests.json", rec["requests_sha256"])
    tokens = read(root / "tokenization.json", rec["tokenization_sha256"])
    pre = raw["preflight"]
    require(
        pre["config"]["n_ctx"] == POLICY["context"]
        and pre["parallel_slots"] == POLICY["slots"]
        and pre["binary_sha256"] == identity["binary_sha256"]
        and pre["backend_tree"] == identity["backend_tree"]
    )
    mapped = pre["actually_loaded_backend_libraries_sha256"]
    require(
        isinstance(mapped, dict)
        and mapped
        and all(re.fullmatch(r"[a-f0-9]{64}", h) for h in mapped.values())
        and digest(mapped) == identity["library_manifest_sha256"]
    )
    require(
        raw["returncode"] == 0
        and raw["stop_reasons"] == []
        and pre["protocol_sha256"] == pinned
        and pre["protocol"] == protocol
        and pre["model_sha256_prior_verified"] == MODEL
        and pre["run_id"] == rec["run_id"]
    )
    require(
        isinstance(pre["server_model_id"], str)
        and pre["server_model_id"]
        and raw["launch_identity"] == pre["launch_identity"]
        and raw["launch_identity"]["pid"] > 0
        and raw["launch_identity"]["start_ticks"] > 0
    )
    require(list(tokens) == IDS and list(requests) == IDS and len(raw["results"]) == 2)
    for row in raw["results"]:
        require(
            all(
                type(row[k]) in (int, float) and math.isfinite(row[k])
                for k in ["started_s", "ended_s"]
            )
            and 0 <= row["started_s"] <= row["ended_s"]
        )
    require(raw["results"][0]["ended_s"] <= raw["results"][1]["started_s"])
    public = []
    for i, (row, spec) in enumerate(zip(raw["results"], specs, strict=True)):
        key = IDS[i]
        messages = users[0] if i == 0 else fixed_second
        if i == 1 and mode == "natural":
            messages = assistant_history_messages(users[0], raw["results"][0]["message"], users[1])
        require(requests[key] == payload(pre["server_model_id"], messages))
        counts, grade = check_response(row, tokens[key], i, spec)
        public.append(
            {
                "input_ids_match": digest(tokens[key]) == manifest["turns"][i]["prompt_ids_sha256"],
                "historical_payload_match": digest(messages)
                == manifest["turns"][i]["messages_sha256"],
                "cache_matches": counts == COUNTS[i],
                "prompt_tokens": counts[0],
                "cached_tokens": counts[1],
                "new_tokens": counts[2],
                "content_pass": grade,
            }
        )
    return {
        "engine": protocol["engine"],
        "identity": {
            k: identity[k]
            for k in ["model_sha256", "binary_sha256", "backend_tree", "library_manifest_sha256"]
        },
        "receipt_sha256": hashlib.sha256((root / "receipt.json").read_bytes()).hexdigest(),
        "raw_sha256": rec["raw_sha256"],
        "run_id_sha256": digest(rec["run_id"]),
        "turns": public,
    }


def compare(root, plan_hash, inputs):
    require(re.fullmatch(r"[0-9a-f]{64}", plan_hash))
    require(sum(p.stat().st_size for p in root.rglob("*") if p.is_file()) <= 256 * 1024**2)
    plan = read(root / "pair.json", plan_hash)
    mode = plan["mode"]
    require(
        plan["schema"] == "tesy-two-turn-pair-v1"
        and mode in {"natural", "fixed"}
        and plan["input_sha256"] == digest(inputs[0])
        and set(plan["arms"]) == ROLES.keys()
    )
    observations = {
        role: arm(root / role, mode, plan_hash, plan["arms"][role], inputs) for role in ROLES
    }
    require(all(observations[k]["engine"] == ROLES[k] for k in ROLES))
    a, b = observations.values()
    require(all(a[k] != b[k] for k in ["run_id_sha256", "raw_sha256", "receipt_sha256"]))
    require(all(a["identity"][k] != b["identity"][k] for k in ["backend_tree", "binary_sha256"]))
    matched = all(
        turn["input_ids_match"] and turn["cache_matches"] and turn["historical_payload_match"]
        for capture in observations.values()
        for turn in capture["turns"]
    )
    outcome = "INCONCLUSIVE_INPUT_OR_CACHE"
    if matched:
        grades = a["turns"][1]["content_pass"], b["turns"][1]["content_pass"]
        outcome = {
            (False, False): "BOTH_FAIL",
            (False, True): "ONLY_R0_FAILS",
            (True, False): "ONLY_REFERENCE_FAILS",
            (True, True): "BOTH_PASS",
        }[grades]
    return {
        "status": "DIAGNOSTICO_PAIRED" if matched else "INCONCLUSIVE",
        "second_turn": outcome,
        "mode": mode,
        "pair_sha256": plan_hash,
        "arms": observations,
    }


def deadline(_signal, _frame):
    raise TimeoutError("time limit")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--historical-results", required=True, type=Path)
    ap.add_argument("--new-output-dir", required=True, type=Path)
    ap.add_argument("--pair-dir", type=Path)
    ap.add_argument("--pair-sha256")
    args = ap.parse_args()
    if bool(args.pair_dir) != bool(args.pair_sha256):
        ap.error("--pair-dir and --pair-sha256 must be supplied together")
    out, history = args.new_output_dir.resolve(), args.historical_results.resolve()
    if out.is_relative_to(history) or (
        args.pair_dir and out.is_relative_to(args.pair_dir.resolve())
    ):
        ap.error("keep the new output outside all input roots")
    out.mkdir()
    report = {"schema": "tesy-two-turn-audit-v1", "physical_inference_by_tool": "NOT_RUN"}
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(60)
    try:
        inputs = prepare(history)
        report.update(
            input_manifest=inputs[0],
            input_sha256=digest(inputs[0]),
            comparison={"status": "NOT_RUN_PAIR_REQUIRED"},
        )
        if args.pair_dir:
            report["comparison"] = compare(args.pair_dir, args.pair_sha256, inputs)
    except FileNotFoundError:
        report["comparison"] = {
            "status": "NOT_RUN_RAW_REQUIRED"
            if "input_manifest" not in report
            else "NOT_RUN_PAIR_REQUIRED"
        }
    except (OSError, GateError, KeyError, IndexError, TypeError, ValueError):
        report["comparison"] = {"status": "FAIL_EVIDENCE"}
    finally:
        signal.alarm(0)
    staging = out / ".pending"
    with staging.open("x") as f:
        json.dump(report, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    os.replace(staging, out / "manifest.json")
    status = report["comparison"]["status"]
    print(status)
    return int(
        status not in {"DIAGNOSTICO_PAIRED", "NOT_RUN_PAIR_REQUIRED"}
        or ("input_manifest" not in report)
        or (args.pair_dir is not None and status == "NOT_RUN_PAIR_REQUIRED")
    )


if __name__ == "__main__":
    raise SystemExit(main())
