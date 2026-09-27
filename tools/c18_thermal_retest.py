#!/usr/bin/env python3
"""C18 prospective CPU100 retest of only cold513 arms stopped under CPU95."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import c2_server_run as server
from c18_cpu_telemetry import capture as cpu_capture, summarize_samples
from c17_thermal_recovery import thermal_idle, no_other_model, check_scope
from c2_gate import GateError, PROTOCOL, strict_json, validate as validate_c2
from c8_observer_runner import model_stat, program_physical_consumed
from c9_server_admission import MODEL, configuration, digest, validate_receipt
from run_bounded import sha256

SPEC = (
    ("c18-p1-p8-cold513", "P8", "cold513", "P1", 1),
    ("c18-p1-p12-cold513", "P12", "cold513", "P1", 2),
    ("c18-p2-p12-cold513", "P12", "cold513", "P2", 1),
    ("c18-p2-p8-cold513", "P8", "cold513", "P2", 2),
)
SPEC_BY_ID = {row[0]: row for row in SPEC}
TOKEN_SHA = "e19cb14e4c38e8f1b153a58c1d3450ded2b402d82f5798961a1246285099d316"
ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = "tesy-c18-cpu100-thermal-retest-20260927T1756Z"
MODEL_SHA = "582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d"
C17_ROOT = ROOT / 'results/c17-thermal-recovery-20260927T1656Z'


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
    timeout = 300
    config.update(suite="c18" + phase.lower(), total_timeout_s=timeout,
                  request_policy={"mode": mode, "attempts": 1, "max_tokens": 4,
                                  "temperature": 0, "seed": 42,
                                  "per_request_timeout_s": timeout - 20,
                                  "prompt_cache": True})
    tasks = []
    source = data["short513"]
    task = {"id": source["id"], "category": "synthetic-resource",
            "prompt": source["prompt"], "cache_prompt": True}
    tasks = [(task["id"], task)]
    config.update(task_ids=[task["id"]], n_ctx=8192, pretokenize=True,
                  freeze_token_ids=True, enforce_output_reserve=True,
                  prompt_token_ranges={task["id"]: source["expected_prompt_tokens"]})
    protocol["identity"].update(config_sha256=digest(config),
                                 workload_sha256=sha256(root / "input.json"),
                                 input_sha256={"input.json": sha256(root / "input.json"),
                                               "usage-contract.json": sha256(root / "usage-contract.json")})
    prior_id = 'c17-t2-p8-cold513' if arm == 'P8' else 'c17-t2-p12-cold513'
    prior_protocol = strict_json((C17_ROOT / 'protocols' / (prior_id + '.json')).read_text())
    prior_config = strict_json((C17_ROOT / 'raw' / (prior_id + '.preflight.json')).read_text())['config']
    common = {'server_command', 'explicit_env', 'request_policy', 'task_ids', 'n_ctx',
              'pretokenize', 'freeze_token_ids', 'enforce_output_reserve',
              'prompt_token_ranges', 'backend_root', 'total_timeout_s'}
    if {key: config[key] for key in common} != {key: prior_config[key] for key in common} or \
            {key: value for key, value in protocol['limits'].items() if key != 'cpu_max_c'} != \
            {key: value for key, value in prior_protocol['limits'].items() if key != 'cpu_max_c'} or \
            any(protocol['identity'][key] != prior_protocol['identity'][key] for key in
                ('model_sha256', 'backend_sha', 'binary_sha256', 'library_sha256',
                 'workload_sha256', 'input_sha256')):
        raise GateError('C18 model/backend/workload/profile differs from interrupted C17 arm')
    protocol.update(campaign_id=CAMPAIGN, protocol_id=run_id + "-v1",
                    expected_request_ids=config["task_ids"])
    prior = protocol.pop("c9")
    protocol['limits']['cpu_max_c'] = 100
    protocol["c18"] = {"run_id": run_id, "arm": arm, "phase": phase, "order": order,
                       "mode": mode, "model_stat": prior["model_stat"],
                       "backend_tree": prior["backend_tree"],
                       "backend_dirty": prior["backend_dirty"],
                       "monitor_sha256": sha256(server.__file__),
                       "gate_sha256": sha256(validate_receipt.__code__.co_filename),
                       "runner_sha256": sha256(__file__),
                       "numerical_scope": "server 8K full-logit reference NOT_RUN",
                       "cpu_warning_c": 95, "cpu_stop_c": 100,
                       "clock_collapse_rule": "five consecutive warning samples below 50% of median of up to 30 prewarning active samples, requiring >=10 prewarning active samples",
                       "explicit_thermal_limit": "any Processor cooling cur_state > 0"}
    return protocol, config, tasks


def run_unit(root, run_id, commit):
    spec = SPEC_BY_ID[run_id]
    protocol, config, tasks = frozen(root, spec)
    protocol_path = root / "protocols" / (run_id + ".json")
    if git("rev-parse", "HEAD") != commit or git("status", "--porcelain") or \
            strict_json(protocol_path.read_text()) != protocol:
        raise GateError("measurement commit/tree or frozen protocol changed")
    if model_stat() != protocol["c18"]["model_stat"] or \
            protocol["identity"]["model_sha256"] != MODEL_SHA:
        raise GateError("model identity changed")
    prior_idle = 394.4515725659985  # preserved C16 blocked idle scope
    prior_idle += sum(strict_json(p.read_text())["duration_s"] for p in C17_ROOT.glob("*-idle.json"))
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
    if cpu_capture()['processor_cooling_max_state'] != 0:
        raise GateError('CPU processor cooling active before idle admission')
    idle = thermal_idle(root, run_id)
    save_x(root / (run_id + "-idle.json"), idle)
    receipt = {"schema": "c18-thermal-unit-v1", "run_id": run_id, "arm": spec[1],
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
    if cpu_capture()['processor_cooling_max_state'] != 0:
        raise GateError('CPU processor cooling active after idle admission')
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
        samples = [strict_json(s) for s in
                   (root / "raw" / (run_id + ".samples.jsonl")).read_text().splitlines()]
        try:
            receipt['cpu_telemetry'] = summarize_samples(samples, require_safe=False)
        except (GateError, KeyError, ValueError, TypeError) as exc:
            receipt['cpu_telemetry_error'] = f'{type(exc).__name__}: {exc}'
        thermal_stops = {'CPU_TJMAX_100', 'CPU_PROCESSOR_COOLING_ACTIVE',
                         'CPU_CLOCK_COLLAPSE_WITH_THERMAL_WARNING', 'THERMAL_GUARD'}
        if any(reason in thermal_stops for reason in raw["stop_reasons"]):
            receipt["status"] = "FAIL_THERMAL_LIMIT"
        elif runner_rc == 0:
            try:
                maxima = validate_receipt(protocol, config, raw, samples, root,
                                          run_id=run_id,
                                          protocol_filename="protocols/" + run_id + ".json",
                                          expected_results=len(tasks))
                receipt.update(maxima=maxima, sample_count=len(samples))
                receipt['cpu_telemetry'] = summarize_samples(samples, require_safe=True)
                normalized = strict_json((root / "raw" / (run_id + ".normalized.json")).read_text())
                receipt["server_gate"] = validate_c2(normalized,
                                                   {k: protocol[k] for k in PROTOCOL})
                tokens = strict_json((root / "raw" / (run_id + ".tokenization.json")).read_text())
                ids = tokens[tasks[0][0]]
                if len(ids) != 513 or digest(ids) != TOKEN_SHA:
                    raise GateError("frozen official token IDs differ")
                result = raw["results"][0]
                if result["usage"]["completion_tokens"] != 4 or \
                        result["usage"]["prompt_tokens"] != len(ids) or \
                        result["timings"]["cache_n"] != 0:
                    raise GateError("incomplete response or unexpected prefix reuse")
                receipt.update(input_token_ids_sha256=digest(ids),
                               output_message_sha256=digest(result["message"]),
                               request_elapsed_s=result['ended_s']-result['started_s'],
                               prefill_s=result["timings"]["prompt_ms"]/1000,
                               decode_s=result["timings"]["predicted_ms"]/1000)
                receipt["status"] = "PASS_QUALIFIED"
                if model_stat() != protocol["c18"]["model_stat"]:
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
        save_x(root / "protocol.json", {"schema": "c18-cpu100-thermal-retest-protocol-v1",
                "checkpoint_commit": "d3beba892d85256c492ee2bf239cea37712646cf",
                "c17_result_commit": git('rev-parse', 'b93a27e'),
                "base_control": "C9 P8 ub32 preload ON; C11 P12 ub32 preload ON",
                "old_fail_classification": "FAIL_PROTOCOL_THERMAL_GUARD, preserved in original C9-C17 receipts",
                "server_backend": "1248fd8fa8cfebaece5ea992e4d951c1e18bb9d5",
                "token_ids_sha256": TOKEN_SHA, "pair_order": ["P8", "P12", "P12", "P8"],
                "phase_order": ["P1", "P2"],
                "primary_pair_metric": "completion-fenced API request elapsed seconds for the single 513+4 request",
                "secondary_pair_metrics": ["backend prefill seconds", "backend four-token decode seconds"],
                "gain_formula": "100*(P8-P12)/P8 with positive P8 denominator, independently for each new pair",
                "performance_policy": "descriptive thermal recovery; no server speed threshold existed in C9/C11 and no timing promotion is inferred",
                "idle_min_s": 300, "idle_max_s": 900, "idle_sample_interval_target_s": 0.5,
                "idle_cadence_rule": "one consecutive >=300 s window, every gap <=1 s; any earlier gap remains recorded",
                "prior_c16_idle_consumed_s": 394.4515725659985,
                "prior_c17_idle_consumed_s": sum(strict_json(p.read_text())["duration_s"] for p in C17_ROOT.glob("*-idle.json")),
                "idle_cpu_limit_c": 55,
                "cooling_condition": "changed_physical_placement (owner report)",
                "ambient_temperature": "UNKNOWN", "profile_changes": ["-ngl 8 vs 12 only"],
                "numeric_limit": "8K server full-logit reference NOT_RUN",
                "cpu_policy": {"warning_at_or_above_c": 95, "stop_at_or_above_c": 100,
                               "stop_on_processor_cooling": True,
                               "stop_on_sustained_clock_collapse": "five consecutive samples below half prewarning median",
                               "tjmax_source": "https://www.amd.com/en/products/processors/laptop/ryzen/ai-300-series/amd-ryzen-ai-9-hx-370.html"},
                "per_run_protocol_sha256": all_protocols,
                "stop_policy": "no hidden retry; preserve all guard/evidence failures"})
        print("frozen", len(SPEC), "C18 unit protocols")
        return 0
    if not args.measurement_commit:
        parser.error("measurement commit required")
    return run_unit(root, args.run, args.measurement_commit)


if __name__ == "__main__":
    sys.exit(main())
