#!/usr/bin/env python3
"""Read-only audit of the C8 confirmation and C9-C14 server receipts."""

import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path

from c2_gate import strict_json


CASES = (
    ("c9-20260927T1441Z", "c9-g1-init", "protocol.json", "P8 ub32 preload ON", "init", "single"),
    ("c9-20260927T1441Z", "c9-g2-forward", "forward-protocol03.json", "P8 ub32 preload ON", "78+4", "single"),
    ("c9-20260927T1441Z", "c9-g3-prefix-on", "prefix-protocol-on02.json", "P8 ub32 preload ON", "513+4 then 641+4", "C9 prefix ON first"),
    ("c10b-20260927T1520Z", "c10b-g1-init", "init-protocol.json", "P8 ub64 preload ON", "init", "single"),
    ("c10b-20260927T1520Z", "c10b-g2-forward", "forward-protocol.json", "P8 ub64 preload ON", "78+4", "single"),
    ("c10b-20260927T1520Z", "c10b-g3-short513", "short513-protocol.json", "P8 ub64 preload ON", "513+4", "single"),
    ("c11-20260927T1533Z", "c11-g1-init", "init-protocol.json", "P12 ub32 preload ON", "init", "single"),
    ("c11-20260927T1533Z", "c11-g2-forward", "forward-protocol.json", "P12 ub32 preload ON", "78+4", "single"),
    ("c11-20260927T1533Z", "c11-g3-short513", "short513-protocol.json", "P12 ub32 preload ON", "513+4", "single"),
    ("c12-20260927T1540Z", "c12-g1-init", "init-protocol.json", "P16 ub32 slots24 preload ON", "init", "single"),
    ("c12-20260927T1540Z", "c12-g2-forward", "forward-protocol.json", "P16 ub32 slots24 preload ON", "78+4", "single"),
    ("c12-20260927T1540Z", "c12-g3-short513", "short513-protocol.json", "P16 ub32 slots24 preload ON", "513+4", "single"),
    ("c13-20260927T1550Z", "c13-g1-prefix-on", "prefix-protocol-on.json", "P12 ub32 preload ON", "513+4 then 641+4", "C13 prefix ON first"),
    ("c14-20260927T1555Z", "c14-g1-init", "init-protocol.json", "P12 ub64 preload ON", "init", "single"),
    ("c14-20260927T1555Z", "c14-g2-forward", "forward-protocol.json", "P12 ub64 preload ON", "78+4", "single"),
    ("c14-20260927T1555Z", "c14-g3-short513", "short513-protocol.json", "P12 ub64 preload ON", "513+4", "single"),
)
TOKEN_SHA = "e19cb14e4c38e8f1b153a58c1d3450ded2b402d82f5798961a1246285099d316"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_run(base, case):
    directory, run_id, protocol_name, profile, workload, order = case
    campaign = base / "results" / directory
    raw_dir = campaign / "raw"
    raw_path = raw_dir / (run_id + ".json")
    row = {"run_id": run_id, "profile": profile, "workload": workload,
           "historical_order": order, "raw": str(raw_path.relative_to(base)),
           "protocol": str((campaign / protocol_name).relative_to(base))}
    if not raw_path.is_file():
        return dict(row, classification="INCOMPLETE_EVIDENCE", reasons=["raw receipt missing"])
    problems = []
    try:
        raw = strict_json(raw_path.read_text())
        protocol_path = campaign / protocol_name
        protocol = strict_json(protocol_path.read_text())
        pre = raw["preflight"]
        if pre["protocol_sha256"] != sha(protocol_path):
            problems.append("frozen protocol hash mismatch")
        if pre["protocol"] != protocol:
            problems.append("embedded protocol mismatch")
        if pre["actually_loaded_backend_libraries_sha256"] != protocol["identity"]["library_sha256"]:
            problems.append("mapped library hash mismatch")
        if raw["preflight"]["model_stat_before"]["size"] != 63387346208:
            problems.append("model size mismatch")
        for suffix, expected in raw["source_sha256"].items():
            source = raw_dir / (run_id + suffix)
            if not source.is_file() or sha(source) != expected:
                problems.append("missing or changed raw " + suffix)
        launch = strict_json((raw_dir / (run_id + ".launch.json")).read_text())
        if launch["preflight_sha256"] != sha(raw_dir / (run_id + ".preflight.json")) or \
                launch["process_identity"] != raw["launch_identity"]:
            problems.append("launch identity/preflight hash mismatch")
        samples = [strict_json(s) for s in (raw_dir / (run_id + ".samples.jsonl")).read_text().splitlines()]
        if len(samples) != raw["sample_count"] or len(samples) < 2:
            problems.append("sample count/endpoints incomplete")
        times = [s["elapsed_s"] for s in samples]
        # Watchdog thermal stops end sampling at the guard-trigger sample; the
        # following server teardown is not a live monitored interval.
        terminal_allowance = 10 if "THERMAL_GUARD" in raw["stop_reasons"] else 2
        if times[0] > 2 or raw["elapsed_s"] - times[-1] > terminal_allowance or \
                any(not 0 < b-a <= 3 for a, b in zip(times, times[1:])) or \
                times[-1] > raw["elapsed_s"] + 0.25:
            problems.append("sample cadence/boundaries invalid")
        identity = raw["launch_identity"]
        if any(s["pid"] != identity["pid"] or s["process_identity"] != identity for s in samples):
            problems.append("sample process identity mismatch")
        start, end = pre["cgroup_start"], raw["cgroup_end"]
        if start["memory_max"] != 18 * 2**30 or start["swap_max"] != 0 or \
                end["swap_max"] != 0 or end["swap_current"] != 0:
            problems.append("cgroup E18/swap invalid")
        event_names = ("max", "oom", "oom_kill", "oom_group_kill")
        event_delta = {scope: {name: end[scope][name] - start[scope][name]
                               for name in event_names} for scope in ("events", "events_local")}
        if any(v for names in event_delta.values() for v in names.values()):
            problems.append("cgroup memory cap/OOM event")
        if any(s["cgroup"]["swap_current"] or s["proc"]["VmSwap"] or \
               s["cgroup"]["swap_max"] != 0 for s in samples):
            problems.append("sample swap used or enabled")
        maxima = {"cpu_c": max(s["thermal"]["cpu_tctl_c"] for s in samples),
                  "gpu_c": max(s["gpu"]["temperature_c"] for s in samples),
                  "nvme_c": max(s["thermal"]["nvme_composite_c"] for s in samples),
                  "gpu_total_mib": max(s["gpu"]["used_mib"] for s in samples),
                  "rss_bytes": max(s["proc"]["VmRSS"] for s in samples),
                  "cgroup_peak_bytes": max(s["cgroup"]["memory_peak"] for s in samples)}
        first_exceed = next((s for s in samples if s["thermal"]["cpu_tctl_c"] > 95 or
                             s["gpu"]["temperature_c"] > 80 or
                             s["thermal"]["nvme_composite_c"] > 70), None)
        tokenization = raw_dir / (run_id + ".tokenization.json")
        input_token_sha = None
        if tokenization.is_file():
            token_ids = strict_json(tokenization.read_text())
            first_ids = next(iter(token_ids.values()))
            input_token_sha = hashlib.sha256(json.dumps(first_ids, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()
            if workload.startswith("513") and (len(first_ids) != 513 or input_token_sha != TOKEN_SHA):
                problems.append("513 token IDs differ from frozen workload")
        if workload.startswith("513") and not tokenization.is_file():
            problems.append("513 tokenization raw missing")
        expected_outputs = len(protocol["expected_request_ids"])
        results = raw["results"]
        output_complete = raw["returncode"] == 0 and not raw["stop_reasons"] and \
                          len(results) == expected_outputs
        if output_complete and expected_outputs:
            output_complete = all(r["usage"]["completion_tokens"] == 4 and
                                  r["usage"]["prompt_tokens"] in (78, 513, 641) and
                                  r["finish_reason"] in ("length", "stop") for r in results)
        if first_exceed:
            first_utc = (datetime.fromisoformat(pre["started_utc"]) +
                         timedelta(seconds=first_exceed["elapsed_s"])).isoformat()
        else:
            first_utc = None
        row.update(returncode=raw["returncode"], stop_reasons=raw["stop_reasons"],
                   elapsed_s=raw["elapsed_s"], output_complete=output_complete,
                   completed_requests=len(results), expected_requests=expected_outputs,
                   input_token_ids_sha256=input_token_sha,
                   initial_temperatures_c={"cpu": samples[0]["thermal"]["cpu_tctl_c"],
                                           "gpu": samples[0]["gpu"]["temperature_c"],
                                           "nvme": samples[0]["thermal"]["nvme_composite_c"]},
                   first_guard_exceed_elapsed_s=first_exceed["elapsed_s"] if first_exceed else None,
                   first_guard_exceed_utc=first_utc, maxima=maxima,
                   cgroup={"memory_max": start["memory_max"], "swap_max": start["swap_max"],
                           "swap_end": end["swap_current"], "memory_peak": end["memory_peak"],
                           "event_delta": event_delta}, sample_count=len(samples),
                   raw_sha256=sha(raw_path))
        if problems:
            row["classification"] = "INCOMPLETE_EVIDENCE"
        elif first_exceed and "THERMAL_GUARD" in raw["stop_reasons"] and not output_complete:
            row["classification"] = "FAIL_THERMAL_GUARD"
        elif output_complete and not first_exceed:
            row["classification"] = "PASS_QUALIFIED"
            row["qualification_scope"] = "resource/process/request only; server numeric and quality not certified"
        else:
            row["classification"] = "FAIL_OTHER"
        row["reasons"] = problems
    except (KeyError, ValueError, OSError, TypeError, IndexError) as exc:
        row.update(classification="INCOMPLETE_EVIDENCE", reasons=[str(exc)])
    return row


def audit_c8(base):
    root = base / "results/c8-20260927T1305Z"
    summary = strict_json((root / "timing496-confirm-summary.json").read_text())
    checks = {}
    for run_id, expected in summary["raw_refs"].items():
        raw = root / "raw" / (run_id + ".json")
        logits = root / "raw" / (run_id + ".f32")
        checks[run_id] = raw.is_file() and logits.is_file() and \
            sha(raw) == expected["manifest_sha256"] and sha(logits) == expected["logits_sha256"] and \
            strict_json(raw.read_text())["returncode"] == 0
    return {"classification": "PASS_QUALIFIED" if all(checks.values()) else "INCOMPLETE_EVIDENCE",
            "scope": "496+32 teacher-forced probe; no 8K serving/session/quality claim",
            "paired_gain_work_median_pct": summary["median_of_paired_gains_pct"]["work_s"],
            "pair_count": summary["new_pairs"], "raw_checks": checks}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    base = Path(__file__).resolve().parents[1]
    runs = [audit_run(base, case) for case in CASES]
    report = {"schema": "c16-thermal-recovery-audit-v1",
              "checkpoint_commit": "d3beba892d85256c492ee2bf239cea37712646cf",
              "classification_rule": "PASS_QUALIFIED applies only to the prior resource/process/request scope; numeric/quality/session coverage stays separate",
              "same_513_token_ids_sha256": TOKEN_SHA,
              "historical_runs": runs,
              "not_run": ["C9 prefix OFF arm", "C13 second prefix request", "C15 compile/profile/model",
                          "M3 session qualification", "M4 functional/main-profile qualification"],
              "c8_preload_confirmation": audit_c8(base)}
    with args.output.open("x") as out:
        json.dump(report, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")
    print(json.dumps({"counts": {s: sum(x["classification"] == s for x in runs)
                                  for s in ("PASS_QUALIFIED", "FAIL_THERMAL_GUARD", "FAIL_OTHER", "INCOMPLETE_EVIDENCE")},
                      "c8": report["c8_preload_confirmation"]["classification"]}))


if __name__ == "__main__":
    main()
