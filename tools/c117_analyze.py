"""No-replace compact analysis of frozen C117 operational server pairs."""

import argparse
import json
import math
from pathlib import Path

from c2_gate import GateError, strict_json
from run_bounded import sha256


ARMS = ((1, "control"), (1, "candidate"), (2, "candidate"), (2, "control"))
METRICS = ("cold_first_final_s", "cold_prefill_s", "cold_decode_s",
           "warm_first_final_s", "warm_prefill_s", "warm_decode_s")


def save_new(path, row):
    with path.open("x") as out:
        json.dump(row, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")


def finite_pos(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise GateError(f"C117 invalid {name}")
    return float(value)


def require_arm_inventory(root, run_id):
    """C117 froze a 60 s, <=1 s cadence inventory before every arm."""
    path = root / "raw" / f"{run_id}.start-inventory.jsonl"
    if not path.is_file():
        raise GateError(f"C117 missing per-arm 60 s inventory: {run_id}")
    rows = [strict_json(line) for line in path.read_text().splitlines()]
    if len(rows) < 61:
        raise GateError(f"C117 short per-arm inventory: {run_id}")
    times = [row.get("elapsed_s") for row in rows]
    if any(type(t) not in (int, float) or not math.isfinite(t) for t in times) or \
       times[0] < 0 or times[-1] - times[0] < 60 or \
       any(not 0 < b - a <= 1.5 for a, b in zip(times, times[1:])):
        raise GateError(f"C117 invalid per-arm inventory cadence: {run_id}")
    return len(rows)


def run_row(root, pair, arm, measurement_commit, resources, *, run_prefix="c117"):
    run_id = f"{run_prefix}-p{pair}-{arm}"
    require_arm_inventory(root, run_id)
    receipt_path = root / "raw" / f"{run_id}.receipt.json"
    raw_path = root / "raw" / f"{run_id}.json"
    receipt, raw = strict_json(receipt_path.read_text()), strict_json(raw_path.read_text())
    if receipt.get("run_id") != run_id or receipt.get("status") != "PASS_SCREEN_ARM_TESTED_SCOPE" or \
       receipt.get("measurement_commit") != measurement_commit or \
       receipt.get("raw_sha256") != sha256(raw_path) or \
       receipt.get("stop_reasons") != [] or raw.get("returncode") != 0 or \
       len(raw.get("results", [])) != 2:
        raise GateError(f"C117 incomplete receipt/raw: {run_id}")
    first, second = raw["results"]
    if first["id"] != "c112-code" or second["id"] != "c112-repeat" or \
       first["usage"]["prompt_tokens"] != 2043 or second["usage"]["prompt_tokens"] != 2197 or \
       first["usage"]["completion_tokens"] != 78 or second["usage"]["completion_tokens"] != 47 or \
       second["timings"]["cache_n"] != 2044 or second["timings"]["prompt_n"] != 153 or \
       first["message"]["content"].strip() != second["message"]["content"].strip() or \
       first["finish_reason"] != "stop" or second["finish_reason"] != "stop":
        raise GateError(f"C117 token/answer mismatch: {run_id}")
    maxima = receipt["maxima"]
    if maxima["swap_bytes"] != 0 or maxima["cpu_c"] >= resources["cpu"]["stop_c"] or \
       maxima["gpu_c"] >= resources["gpu"]["stop_c"] or \
       maxima["gpu_total_mib"] > resources["gpu"]["memory_stop_total_mib"] or \
       maxima["nvme_c"] >= resources["nvme"][0]["stop_c"]:
        raise GateError(f"C117 resource violation: {run_id}")
    metrics = {
        "cold_first_final_s": finite_pos(first["stream_metrics"]["first_final_content_chunk_s"], "cold first final"),
        "cold_prefill_s": finite_pos(first["timings"]["prompt_ms"] / 1000, "cold prefill"),
        "cold_decode_s": finite_pos(first["timings"]["predicted_ms"] / 1000, "cold decode"),
        "warm_first_final_s": finite_pos(second["stream_metrics"]["first_final_content_chunk_s"], "warm first final"),
        "warm_prefill_s": finite_pos(second["timings"]["prompt_ms"] / 1000, "warm prefill"),
        "warm_decode_s": finite_pos(second["timings"]["predicted_ms"] / 1000, "warm decode"),
    }
    start = receipt["matched_start"]
    if start["status"] != "OPERATIONAL_WARM_START_OBSERVED":
        raise GateError(f"C117 start observation missing: {run_id}")
    return {"run_id": run_id, "arm": arm, "pair": pair, "metrics": metrics,
            "decode_tok_s_warm": 47 / metrics["warm_decode_s"],
            "start_cpu_gpu_nvme_c": start["temperature_c"], "maxima": maxima,
            "raw_sha256": receipt["raw_sha256"], "receipt_sha256": sha256(receipt_path)}


def analyze(root):
    policy = strict_json((root / "confirm-policy.json").read_text())
    if policy["order"] != [f"c117-p{p}-{a}" for p, a in ARMS] or \
       policy["primary"] != "warm first_final_content_s":
        raise GateError("C117 policy changed")
    preflight = strict_json((root / "preflight.json").read_text())
    if preflight["confirm_policy_sha256"] != sha256(root / "confirm-policy.json"):
        raise GateError("C117 policy SHA changed")
    resources = strict_json((root / "resource-policy.json").read_text())
    commit = strict_json((root / "raw" / "c117-p1-control.receipt.json").read_text())["measurement_commit"]
    if type(commit) is not str or len(commit) != 40:
        raise GateError("C117 measurement commit absent")
    runs = [run_row(root, p, a, commit, resources) for p, a in ARMS]
    pairs = []
    for pair in (1, 2):
        control = next(row for row in runs if row["pair"] == pair and row["arm"] == "control")
        candidate = next(row for row in runs if row["pair"] == pair and row["arm"] == "candidate")
        gains = {key: 100 * (control["metrics"][key] - candidate["metrics"][key]) / control["metrics"][key]
                 for key in METRICS}
        pairs.append({"pair": pair, "control": control["run_id"], "candidate": candidate["run_id"],
                      "gain_percent": gains,
                      "start_delta_candidate_minus_control_c": [b - a for a, b in zip(control["start_cpu_gpu_nvme_c"], candidate["start_cpu_gpu_nvme_c"])]})
    medians = {key: (pairs[0]["gain_percent"][key] + pairs[1]["gain_percent"][key]) / 2
               for key in METRICS}
    screen = medians["warm_first_final_s"] >= 5 and all(p["gain_percent"]["warm_first_final_s"] > 0 for p in pairs) and \
             medians["warm_decode_s"] >= -5 and medians["cold_decode_s"] >= -5
    timing = {"schema": "c117-timing-pairs-v1", "measurement_commit": commit,
              "runs": runs, "pairs": pairs, "median_paired_gain_percent": medians,
              "metric_authority": "server completion-fenced stream first-final and llama prompt/predicted timings",
              "start_regime": "OPERATIONAL_WARM_UNMATCHED_TEMPERATURES"}
    resource = {"schema": "c117-resource-summary-v1", "runs": [
        {"run_id": row["run_id"], "start_cpu_gpu_nvme_c": row["start_cpu_gpu_nvme_c"],
         "maxima": row["maxima"]} for row in runs],
        "all_resource_receipts_pass": True, "cpu_95_is_warning": True}
    decision = {"schema": "c117-decision-v1",
                "status": "SCREEN_GO_OPERATIONAL_NOMINAL128" if screen else "NO_GO_SCREEN_OPERATIONAL_NOMINAL128",
                "measurement_commit": commit, "pairs": pairs,
                "median_paired_gain_percent": medians,
                "candidate_median_warm_first_final_s": sum(row["metrics"]["warm_first_final_s"] for row in runs if row["arm"] == "candidate") / 2,
                "candidate_median_warm_decode_tok_s": sum(row["decode_tok_s_warm"] for row in runs if row["arm"] == "candidate") / 2,
                "resource_gate": "PASS_FOUR_ARMS", "same_profile_teacher_forced_fidelity": "C111_TESTED_SCOPE_ONLY",
                "server_full_logits": "NOT_RUN", "M3": "C52B_TESTED_SCOPE_UNCHANGED",
                "M4": "NOT_DEMONSTRATED", "confirmation": "NOT_RUN",
                "claim_limits": ["two alternating operational-start pairs, no narrow thermal matching",
                                 "synthetic two-turn task, not diverse session",
                                 "same output text and token counts do not prove sampling-distribution equality",
                                 "C100 NO_GO_CONFIRM remains valid for its workload and protocol"],
                "old_failures_preserved": ["C48", "C100", "C109", "C112", "C113", "C114"],
                "next_action": "three new paired nominal153 server confirmation runs under prospectively frozen operational-start regime if admitted in a later epoch; otherwise directed warm153 trace for decode mechanism",
                "default_changed": False, "publication": "LOCAL_ONLY"}
    manifest = {"schema": "c117-manifest-v1", "measurement_commit": commit,
                "raw": {path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
                        for path in sorted((root / "raw").iterdir()) if path.is_file()},
                "protocol_sha256": {path.name: sha256(path) for path in sorted((root / "protocols").glob("*.json"))}}
    return timing, resource, decision, manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    timing, resource, decision, manifest = analyze(root)
    for name, row in (("timing-pairs.json", timing), ("resource-summary.json", resource),
                      ("decision.json", decision), ("manifest.json", manifest)):
        save_new(root / name, row)
    print(json.dumps({"status": decision["status"], "median_paired_gain_percent": decision["median_paired_gain_percent"]}))


if __name__ == "__main__":
    main()
