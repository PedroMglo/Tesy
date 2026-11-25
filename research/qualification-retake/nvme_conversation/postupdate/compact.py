"""Compact a closed post-update C281 run. Only numbers, statuses and file digests are public."""

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def old_checker(repo):
    folder = repo / "research/qualification-retake/nvme_conversation"
    sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location("tesy_old_c281_compact", folder / "compact.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def request_status(raw):
    phases = []
    for i in (1, 2):
        journal = raw / f"T{i}-request.jsonl"
        phase = {
            "turn": i,
            "input_saved": (raw / f"T{i}-input.json").is_file(),
            "request_started": False,
            "received_sse": False,
            "response_complete": False,
            "terminal_observed": False,
            "accepted": False,
        }
        if journal.is_file():
            previous = first = None
            for line in journal.read_bytes().splitlines():
                r = json.loads(line)
                ts = r["monotonic_s"]
                need(previous is None or previous <= ts, "request clock regressed")
                previous = ts
                kind = r["kind"]
                if kind == "REQUEST_START":
                    need(first is None, "duplicate request start")
                    first = ts
                    phase["request_started"] = True
                if kind == "SSE_FRAGMENT":
                    phase["received_sse"] = True
                if kind == "RESPONSE_COMPLETE":
                    phase["response_complete"] = True
                if kind == "REQUEST_TERMINAL":
                    phase.update(terminal_observed=True, accepted=r["accepted"] is True)
            if first is not None and previous is not None:
                phase["journal_last_minus_start_s"] = previous - first
        # A rejected HTTP response can still have useful transport and server clocks.
        snapshots = [raw / f"T{i}-result.json", raw / f"T{i}-complete-unvalidated.json"]
        full = next((p for p in snapshots if p.is_file()), None)
        if full is not None:
            row = read(full)
            t = row.get("timings", {})
            phase["returned_response"] = {
                "completion_n": row.get("usage", {}).get("completion_tokens"),
                "cache_n": t.get("cache_n"),
                "prompt_n": t.get("prompt_n"),
                "predicted_n": t.get("predicted_n"),
                "prefill_ms": t.get("prompt_ms"),
                "decode_ms": t.get("predicted_ms"),
                "transport_complete_s": row.get("request_wall_s"),
                "first_final_s": row.get("stream_metrics", {}).get("first_final_content_chunk_s"),
                "done_observed": row.get("stream_metrics", {}).get("done_observed", False),
                "finish_reason": row.get("finish_reason")
                if row.get("finish_reason") in ("stop", "length", None)
                else "OTHER",
            }
            if phase["terminal_observed"]:
                phase["terminal_minus_request_start_s"] = (
                    previous - row["request_started_monotonic"]
                )

        phases.append(phase)
    return phases


def summarize(repo, root, receipt_sha):
    receipt_path = root / "receipt.json"
    need(
        receipt_path.is_file() and sha(receipt_path) == receipt_sha, "unclosed or unpinned session"
    )
    result = read(receipt_path)
    status = result["status"]
    ok = "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY"
    need(status in {"FAIL_PRESERVED", ok}, "receipt is not a physical terminal result")
    raw = root / "raw"
    phases = request_status(raw)
    n = len(list(raw.glob("*.launch.json")))
    need(n == result["model_launches"] and n <= 1, "model launch denominator")
    compact = {
        "status": status,
        "raw_receipt_sha256": receipt_sha,
        "model_launches": n,
        "turns": phases,
        "requests_started": sum(p["request_started"] for p in phases),
        "responses_with_sse": sum(p["received_sse"] for p in phases),
        "responses_transport_complete": sum(p["response_complete"] for p in phases),
        "requests_accepted": sum(p["accepted"] for p in phases),
        "envelope_s": result["envelope_s"],
        "physical_energy_j": None,
        "model_forwards": "NOT_INSTRUMENTED",
    }
    if status == "FAIL_PRESERVED":
        failure = result["failure"]
        compact["failure_message_sha256"] = hashlib.sha256(failure.encode()).hexdigest()
        compact["last_confirmed"] = {
            f: (root / f).is_file()
            for f in (
                "qualified-start.json",
                "preset.json",
                "argv.json",
                "first-client-map.json",
                "last-client-map.json",
                "client-receipt.json",
                "serve-receipt.json",
                "qualified-loader.json",
            )
        }
        return compact
    need(
        n == 1
        and all(p["accepted"] and p["received_sse"] and p["response_complete"] for p in phases),
        "successful receipt without two complete validated streams",
    )
    historic = old_checker(repo).summarize(root)
    need(historic["requests"] == historic["valid_requests"] == 2, "historical gate")
    # Retain sanitized summaries and a digest of the full file manifest.
    manifest = historic.pop("local_manifest")
    historic["local_files"] = len(manifest)
    historic["files_sha256"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    auth = result["runtime_authority"]
    start = read(root / "qualified-start.json")
    for k, v in start.items():
        need(auth[k] == v, "runtime start/finish mismatch")
    need(
        auth["status"] == "PASS_LIVE_AND_LOADER_C281"
        and auth["c270_sha256"] == historic["c270_receipt_sha256"],
        "new runtime gate",
    )
    loader_path = root / "qualified-loader.json"
    need(sha(loader_path) == auth["loader_audit_sha256"], "loader summary")
    loader = read(loader_path)
    pid = auth["native_pid"]
    need(
        loader["native_pid"] == pid
        and loader["loader_sha256"] == auth["loader_raw_sha256"] == sha(raw / f"loader.{pid}"),
        "loader raw digest",
    )
    need(auth["original_monitor_sha256"] == result["monitor_sha256"], "monitor identity")
    phases_by_name = [
        ("first_client", "first-client-map.json", "READY_BEFORE_FIRST_POST"),
        ("last_client", "last-client-map.json", "AFTER_SECOND_ACCEPT_BEFORE_STOP"),
    ]
    map_counts = {}
    for field, name, expected in phases_by_name:
        path = root / name
        obj = read(path)
        need(
            auth[field] == sha(path) and obj["pid"] == pid and obj["point"] == expected,
            "live maps proof",
        )
        need(
            obj["mapped_sha256"].items() <= loader["initialized_sha256"].items(), "unconfirmed map"
        )
        map_counts[field] = len(obj["mapped_sha256"])
    run = historic["unit"]
    inv = raw / (run + ".start-inventory.jsonl")
    need(sha(inv) == result["start_inventory"], "C118 identity")
    monitor = read(raw / (run + ".json"))
    inventory_receipt = raw / (run + ".start-inventory.receipt.json")
    inventory = read(inventory_receipt)
    check_count = sum(bool(line) for line in inv.read_bytes().splitlines())
    need(
        inventory["sample_count"] == check_count
        and inventory["sha256"] == sha(inv)
        and sha(inventory_receipt) == monitor["start_inventory"]["receipt_sha256"],
        "C118 samples",
    )
    duration = inventory["duration_s"]
    compact.update(historic)
    compact.update(
        preflight_sha256=auth["preflight_sha256"],
        protocol_driver_sha256=auth["protocol_sha256"],
        C270_grade_sha256=auth["selected_sha256"],
        C270_loader_sha256=auth["c270_loader_sha256"],
        static_map_sha256=auth["static_map_sha256"],
        kernel=auth["kernel"],
        deployment_commit=auth["deployment_commit"],
        monitor_provider=auth["monitor"],
        runtime_status=auth["status"],
        live_counts=map_counts,
        driver_providers=loader["driver_providers"],
        loader_sha256=loader["loader_sha256"],
        initialized_objects=len(loader["initialized_sha256"]),
        C118_duration_s=duration,
        C118_samples=check_count,
        C118_sha256=sha(inv),
    )
    return compact


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "raw-root", "new-output-dir"):
        ap.add_argument("--" + name, required=True, type=Path)
    ap.add_argument("--receipt-sha256", required=True)
    a = ap.parse_args()
    output = summarize(
        a.repo.resolve(strict=True), a.raw_root.resolve(strict=True), a.receipt_sha256
    )
    a.new_output_dir.mkdir(mode=0o700)
    with (a.new_output_dir / "evidence.json").open("x") as fo:
        json.dump(output, fo, sort_keys=True, indent=2, allow_nan=False)
        fo.write("\n")
