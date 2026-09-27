#!/usr/bin/env python3
"""C17 E18 server recovery, using the existing C2 server monitor and C9 gates."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import c2_server_run as server
from c2_gate import GateError, PROTOCOL, strict_json, validate as validate_c2
from c8_observer_runner import model_stat, program_physical_consumed
from c9_server_admission import MODEL, configuration, digest, validate_receipt
from run_bounded import sha256

SPEC = (
    ("c17-t0-p8-init", "P8", "init", "T0", 1),
    ("c17-t0-p12-init", "P12", "init", "T0", 2),
    ("c17-t1-p8-smoke78", "P8", "smoke78", "T1", 1),
    ("c17-t1-p12-smoke78", "P12", "smoke78", "T1", 2),
    ("c17-t2-p8-cold513", "P8", "cold513", "T2", 1),
    ("c17-t2-p12-cold513", "P12", "cold513", "T2", 2),
    ("c17-t3-p12-cold513", "P12", "cold513", "T3", 1),
    ("c17-t3-p8-cold513", "P8", "cold513", "T3", 2),
)
SPEC_BY_ID = {row[0]: row for row in SPEC}
TOKEN_SHA = {"smoke78": "62a2b46ce58d071394cec42017803545b41f5b4c46e97ec754edbd31e97999ac",
             "cold513": "e19cb14e4c38e8f1b153a58c1d3450ded2b402d82f5798961a1246285099d316"}
ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = "tesy-c17-thermal-recovery-20260927"
MODEL_SHA = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"


def save_x(path, value):
    with path.open("x") as out:
        json.dump(value, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def frozen(root, spec):
    run_id, arm, mode, phase, order = spec
    protocol, config = configuration(root)
    data = strict_json((root / "input.json").read_text())
    command = config["server_command"]
    assert command[command.index("-ngl") + 1] == "8"
    command[command.index("-ngl") + 1] = "8" if arm == "P8" else "12"
    timeout = {"init": 120, "smoke78": 180, "cold513": 300}[mode]
    config.update(suite="c17" + phase.lower(), total_timeout_s=timeout,
                  request_policy={"mode": mode, "attempts": 1, "max_tokens": 4,
                                  "temperature": 0, "seed": 42,
                                  "per_request_timeout_s": timeout - 20,
                                  "prompt_cache": True})
    tasks = []
    if mode != "init":
        source = data["minimum_forward" if mode == "smoke78" else "short513"]
        task = {"id": source["id"], "category": "synthetic-resource",
                "prompt": source["prompt"], "cache_prompt": True}
        tasks = [(task["id"], task)]
        config.update(task_ids=[task["id"]], n_ctx=8192, pretokenize=True,
                      freeze_token_ids=True, enforce_output_reserve=True,
                      prompt_token_ranges={task["id"]: source["expected_prompt_tokens"]})
    protocol.update(campaign_id=CAMPAIGN, protocol_id=run_id + "-v1",
                    expected_request_ids=config["task_ids"])
    protocol["identity"].update(config_sha256=digest(config),
                                 workload_sha256=sha256(root / "input.json"),
                                 input_sha256={"input.json": sha256(root / "input.json"),
                                               "usage-contract.json": sha256(root / "usage-contract.json")})
    prior = protocol.pop("c9")
    protocol["c17"] = {"run_id": run_id, "arm": arm, "phase": phase, "order": order,
                       "mode": mode, "model_stat": prior["model_stat"],
                       "backend_tree": prior["backend_tree"],
                       "backend_dirty": prior["backend_dirty"],
                       "monitor_sha256": sha256(server.__file__),
                       "gate_sha256": sha256(validate_receipt.__code__.co_filename),
                       "runner_sha256": sha256(__file__),
                       "numerical_scope": "server 8K full-logit reference NOT_RUN"}
    return protocol, config, tasks


def gpu_snapshot():
    raw = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used,temperature.gpu,driver_version",
                                   "--format=csv,noheader,nounits"], text=True, timeout=8)
    parts = [x.strip() for x in raw.strip().split(",")]
    if len(parts) != 3:
        raise GateError("GPU telemetry missing/ambiguous")
    return {"used_mib": float(parts[0]), "temperature_c": float(parts[1]),
            "driver": parts[2]}


def idle_snapshot(run_id, since):
    sensors = strict_json(subprocess.check_output(["sensors", "-j"], text=True, timeout=8))
    cpu = next(v["Tctl"]["temp1_input"] for k, v in sensors.items() if k.startswith("k10temp-"))
    nvme = next(v["Composite"]["temp1_input"] for k, v in sensors.items() if k.startswith("nvme-"))
    fan = next((v for k, v in sensors.items() if k.startswith("asus-") and "cpu_fan" in v), {})
    mem = next(int(s.split()[1]) * 1024 for s in Path("/proc/meminfo").read_text().splitlines()
               if s.startswith("MemAvailable:"))
    return {"run_id": run_id, "elapsed_s": time.monotonic() - since,
            "utc": datetime.now(timezone.utc).isoformat(), "cpu_c": cpu, "nvme_c": nvme,
            "gpu": gpu_snapshot(), "mem_available_bytes": mem,
            "cpu_fan_rpm": fan.get("cpu_fan", {}).get("fan1_input"),
            "gpu_fan_rpm": fan.get("gpu_fan", {}).get("fan2_input")}


def select_contiguous_window(rows, minimum_s=300, maximum_gap_s=1.0):
    """Return an actual complete window after the last cadence break, if any."""
    if not rows:
        return None
    segment_start = 0
    for index in range(1, len(rows)):
        if rows[index]["elapsed_s"] - rows[index-1]["elapsed_s"] > maximum_gap_s:
            segment_start = index
    for index in range(len(rows)-1, segment_start-1, -1):
        if rows[-1]["elapsed_s"] - rows[index]["elapsed_s"] >= minimum_s:
            return rows[index:]
    return None


def thermal_idle(root, run_id):
    start = time.monotonic()
    series = root / "thermal-series.jsonl"
    rows = []
    segment = []
    cadence_breaks = []
    baseline_path = root / "baseline.json"
    baseline = strict_json(baseline_path.read_text()) if baseline_path.exists() else None
    with series.open("a") as out:
        while True:
            row = idle_snapshot(run_id, start)
            if segment and row["elapsed_s"] - segment[-1]["elapsed_s"] > 1.0:
                cadence_breaks.append({"before_s": segment[-1]["elapsed_s"],
                                       "after_s": row["elapsed_s"],
                                       "gap_s": row["elapsed_s"] - segment[-1]["elapsed_s"]})
                segment = []
            segment.append(row)
            rows.append(row)
            out.write(json.dumps(row, allow_nan=False) + "\n")
            out.flush()
            qualifying = select_contiguous_window(rows)
            if qualifying is not None or row["elapsed_s"] >= 900:
                window = [s for s in (qualifying or segment)
                          if s["elapsed_s"] >= row["elapsed_s"] - 60]
                first = window[:min(10, len(window))]
                last = window[-min(10, len(window)):]
                trend = {k: sum(s[k] for s in last)/len(last) -
                         sum(s[k] for s in first)/len(first) for k in ("cpu_c", "nvme_c")}
                trend["gpu_c"] = (sum(s["gpu"]["temperature_c"] for s in last)/len(last) -
                                  sum(s["gpu"]["temperature_c"] for s in first)/len(first))
                max_gap = max(b["elapsed_s"]-a["elapsed_s"] for a,b in zip(rows,rows[1:]))
                qualifying_gap = (max(b["elapsed_s"]-a["elapsed_s"] for a,b in
                                      zip(qualifying,qualifying[1:])) if qualifying else None)
                admissible = (qualifying is not None and qualifying_gap <= 1.0 and
                              all(s["cpu_c"] <= 55 and s["nvme_c"] <= 55 and
                                  s["gpu"]["temperature_c"] <= 55 for s in qualifying) and
                              all(x <= 2 for x in trend.values()) and
                              row["mem_available_bytes"] >= 6*2**30 and
                              row["gpu"]["used_mib"] < 100 and
                              (baseline is None or
                               abs(row["cpu_c"] - baseline["cpu_c"]) <= 2 and
                               abs(row["gpu"]["temperature_c"] - baseline["gpu_c"]) <= 3 and
                               abs(row["nvme_c"] - baseline["nvme_c"]) <= 3))
                if admissible or row["elapsed_s"] >= 900:
                    return {"status": "PASS" if admissible else "THERMAL_PREFLIGHT_BLOCKED",
                            "sample_count": len(rows), "duration_s": row["elapsed_s"],
                            "max_gap_overall_s": max_gap,
                            "max_gap_qualifying_s": qualifying_gap,
                            "qualifying_start_s": qualifying[0]["elapsed_s"] if qualifying else None,
                            "qualifying_duration_s": row["elapsed_s"]-qualifying[0]["elapsed_s"] if qualifying else None,
                            "cadence_breaks": cadence_breaks,
                            "start": rows[0], "end": row, "last60_trend_c": trend,
                            "baseline": baseline, "series_sha256": sha256(series)}
            next_at = start + len(rows) * 0.5
            time.sleep(max(0, next_at - time.monotonic()))


def no_other_model():
    apps = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid,process_name,used_gpu_memory",
                                    "--format=csv,noheader"], text=True, timeout=8).strip()
    if apps:
        raise GateError("GPU compute process already active: " + apps[:200])


def check_scope():
    cg = server.cgroup_state()
    if not cg or cg["memory_max"] != 18*2**30 or cg["swap_max"] != 0 or cg["swap_current"]:
        raise GateError("E18 zero-swap scope unavailable")
    return cg["path"]


def run_unit(root, run_id, commit):
    spec = SPEC_BY_ID[run_id]
    protocol, config, tasks = frozen(root, spec)
    protocol_path = root / "protocols" / (run_id + ".json")
    if git("rev-parse", "HEAD") != commit or git("status", "--porcelain") or \
            strict_json(protocol_path.read_text()) != protocol:
        raise GateError("measurement commit/tree or frozen protocol changed")
    if model_stat() != protocol["c17"]["model_stat"] or \
            protocol["identity"]["model_sha256"] != MODEL_SHA:
        raise GateError("model identity changed")
    prior_idle = 394.4515725659985  # preserved C16 blocked idle scope
    prior_idle += sum(strict_json(p.read_text())["duration_s"] for p in root.glob("*-idle.json"))
    if program_physical_consumed() + prior_idle + 900 + config["total_timeout_s"] + 30 > 16*3600:
        raise GateError("program physical budget insufficient")
    preflight = strict_json((root / "preflight.json").read_text())
    if preflight["guard_status"] != "READY_FOR_IDLE_ADMISSION" or \
            preflight["power_source"] != "AC" or \
            Path("/sys/class/power_supply/AC0/online").read_text().strip() != "1" or \
            subprocess.check_output(["powerprofilesctl", "get"], text=True).strip() != preflight["power_profile"]:
        raise GateError("physical/power preflight changed")
    if any((root / "raw" / (run_id + suffix)).exists() for suffix in
           (".json", ".preflight.json", ".samples.jsonl")):
        raise GateError("no-replace run already exists")
    scope = check_scope()
    no_other_model()
    idle = thermal_idle(root, run_id)
    save_x(root / (run_id + "-idle.json"), idle)
    receipt = {"schema": "c17-thermal-unit-v1", "run_id": run_id, "arm": spec[1],
               "mode": spec[2], "phase": spec[3], "order": spec[4],
               "measurement_commit": commit, "scope": scope, "idle": idle,
               "status": idle["status"], "default_changed": False}
    if idle["status"] != "PASS":
        save_x(root / (run_id + "-receipt.json"), receipt)
        with (root / "runs.jsonl").open("a") as out:
            out.write(json.dumps(receipt, allow_nan=False) + "\n")
        return 2
    if check_scope() != scope or \
            Path("/sys/class/power_supply/AC0/online").read_text().strip() != "1" or \
            subprocess.check_output(["powerprofilesctl", "get"], text=True).strip() != preflight["power_profile"]:
        raise GateError("scope or power condition changed after idle")
    no_other_model()
    if run_id == SPEC[0][0]:
        save_x(root / "baseline.json", {"cpu_c": idle["end"]["cpu_c"],
               "gpu_c": idle["end"]["gpu"]["temperature_c"],
               "nvme_c": idle["end"]["nvme_c"]})
    args = SimpleNamespace(model="target120b", suite=config["suite"], run_id=run_id,
                           protocol=protocol_path)
    try:
        runner_rc = server.run(args, protocol, config, tasks, MODEL)
        launch_error = None
    except (GateError, OSError, RuntimeError, ValueError) as exc:
        runner_rc = 1
        launch_error = f"{type(exc).__name__}: {exc}"
    raw_path = root / "raw" / (run_id + ".json")
    receipt.update(status="FAIL_RESOURCES_OR_EVIDENCE", runner_returncode=runner_rc,
                   launch_error=launch_error, raw_sha256=sha256(raw_path) if raw_path.exists() else None)
    if raw_path.exists():
        raw = strict_json(raw_path.read_text())
        receipt.update(returncode=raw["returncode"], stop_reasons=raw["stop_reasons"],
                       server_elapsed_s=raw["elapsed_s"], completed_requests=len(raw["results"]))
        if "THERMAL_GUARD" in raw["stop_reasons"]:
            receipt["status"] = "FAIL_THERMAL_GUARD"
        elif runner_rc == 0:
            try:
                samples = [strict_json(s) for s in
                           (root / "raw" / (run_id + ".samples.jsonl")).read_text().splitlines()]
                maxima = validate_receipt(protocol, config, raw, samples, root,
                                          run_id=run_id,
                                          protocol_filename="protocols/" + run_id + ".json",
                                          expected_results=len(tasks))
                receipt.update(maxima=maxima, sample_count=len(samples))
                if tasks:
                    normalized = strict_json((root / "raw" / (run_id + ".normalized.json")).read_text())
                    receipt["server_gate"] = validate_c2(normalized,
                                                       {k: protocol[k] for k in PROTOCOL})
                    tokens = strict_json((root / "raw" / (run_id + ".tokenization.json")).read_text())
                    ids = tokens[tasks[0][0]]
                    if len(ids) != (78 if spec[2] == "smoke78" else 513) or digest(ids) != TOKEN_SHA[spec[2]]:
                        raise GateError("frozen official token IDs differ")
                    result = raw["results"][0]
                    if result["usage"]["completion_tokens"] != 4 or \
                            result["usage"]["prompt_tokens"] != len(ids) or \
                            result["timings"]["cache_n"] != 0:
                        raise GateError("incomplete response or unexpected prefix reuse")
                    receipt.update(input_token_ids_sha256=digest(ids),
                                   output_message_sha256=digest(result["message"]),
                                   prefill_s=result["timings"]["prompt_ms"]/1000,
                                   decode_s=result["timings"]["predicted_ms"]/1000)
                if spec[2] == "smoke78":
                    tail = samples[-10:]
                    rise = tail[-1]["thermal"]["cpu_tctl_c"] - tail[0]["thermal"]["cpu_tctl_c"]
                    receipt["smoke_final_cpu_rise_c"] = rise
                    if maxima["cpu_c"] >= 92 or rise > 2:
                        receipt["status"] = "THERMAL_HEADROOM_INSUFFICIENT"
                    else:
                        receipt["status"] = "PASS_QUALIFIED"
                else:
                    receipt["status"] = "PASS_QUALIFIED"
                if model_stat() != protocol["c17"]["model_stat"]:
                    raise GateError("model file metadata changed")
            except (GateError, KeyError, ValueError, OSError, TypeError) as exc:
                receipt.update(status="FAIL_RESOURCES_OR_EVIDENCE", reason=f"{type(exc).__name__}: {exc}")
    save_x(root / (run_id + "-receipt.json"), receipt)
    with (root / "runs.jsonl").open("a") as out:
        out.write(json.dumps({k:v for k,v in receipt.items() if k != "idle"},allow_nan=False) + "\n")
    print(json.dumps({"run_id": run_id, "status": receipt["status"],
                      "cpu_max": receipt.get("maxima",{}).get("cpu_c"),
                      "prefill_s": receipt.get("prefill_s")}, allow_nan=False), flush=True)
    return 0 if receipt["status"] == "PASS_QUALIFIED" else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--freeze", action="store_true")
    choice.add_argument("--run", choices=SPEC_BY_ID)
    parser.add_argument("--measurement-commit")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.freeze:
        (root / "protocols").mkdir(exist_ok=False)
        all_protocols = {}
        for spec in SPEC:
            protocol, _, _ = frozen(root, spec)
            path = root / "protocols" / (spec[0] + ".json")
            save_x(path, protocol)
            all_protocols[spec[0]] = sha256(path)
        save_x(root / "protocol.json", {"schema": "c17-thermal-recovery-protocol-v1",
                "checkpoint_commit": "d3beba892d85256c492ee2bf239cea37712646cf",
                "base_control": "C9 P8 ub32 preload ON; C11 P12 ub32 preload ON",
                "server_backend": "1248fd8fa8cfebaece5ea992e4d951c1e18bb9d5",
                "token_ids_sha256": TOKEN_SHA, "pair_order": ["P8", "P12", "P12", "P8"],
                "phase_order": ["T0", "T1", "T2", "T3"],
                "primary_pair_metric": "completion-fenced API request elapsed seconds for the single 513+4 request",
                "secondary_pair_metrics": ["backend prefill seconds", "backend four-token decode seconds"],
                "gain_formula": "100*(P8-P12)/P8 with positive P8 denominator, independently for each new pair",
                "performance_policy": "descriptive thermal recovery; no server speed threshold existed in C9/C11 and no timing promotion is inferred",
                "idle_min_s": 300, "idle_max_s": 900, "idle_sample_interval_target_s": 0.5,
                "idle_cadence_rule": "one consecutive >=300 s window, every gap <=1 s; any earlier gap remains recorded",
                "prior_c16_idle_consumed_s": 394.4515725659985,
                "idle_cpu_limit_c": 55,
                "cooling_condition": "changed_physical_placement (owner report)",
                "ambient_temperature": "UNKNOWN", "profile_changes": ["-ngl 8 vs 12 only"],
                "numeric_limit": "8K server full-logit reference NOT_RUN",
                "per_run_protocol_sha256": all_protocols,
                "stop_policy": "no hidden retry; preserve all guard/evidence failures"})
        print("frozen", len(SPEC), "C17 unit protocols")
        return 0
    if not args.measurement_commit:
        parser.error("measurement commit required")
    return run_unit(root, args.run, args.measurement_commit)


if __name__ == "__main__":
    sys.exit(main())
