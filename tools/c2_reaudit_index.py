#!/usr/bin/env python3
"""Index local historical reanalysis without changing the original campaign files."""

import hashlib
import json
from pathlib import Path
import subprocess

from c2_gate import GateError, strict_json


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
SERVER = ("task20b-stock-eval02", "task120b-stream24-eval01")
CLI = ("target120b-gpu8-two-turns-slot32-01", "target120b-gpu8-cap32-ab24-01",
       "target120b-gpu8-cap32-ab24-02", "target120b-gpu8-two-turns-slot32-02",
       "target120b-gpu8-two-turns-slot32-03", "target120b-gpu8-cap32-ab24-03")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def read(name):
    return strict_json((RESULTS / name).read_text())


def main():
    source_names = ["campaign-summary.json", "m3-capacity32-ab-summary.json",
                    "m6-paired-summary.json", "c2-legacy-m3-capacity32-reaudit.json"]
    for run in SERVER:
        source_names += [f"{run}{ext}" for ext in (".json", ".stderr", ".samples.jsonl")]
        source_names += [f"c2-legacy-{run}-analysis.json", f"c2-host-{run}-grade.json",
                         f"{run}-judgment.json"]
    for run in CLI:
        source_names += [f"{run}{ext}" for ext in (".json", ".stderr", ".stdout", ".samples.jsonl")]
    hashes = {name: digest(RESULTS / name) for name in source_names}
    server = {}
    for run in SERVER:
        manifest = read(f"{run}.json")
        report = read(f"c2-legacy-{run}-analysis.json")
        ids = manifest["task_ids"]
        if ids != [x["task_id"] for x in manifest["results"]] or len(ids) != len(set(ids)):
            raise GateError(f"historical task IDs do not match: {run}")
        if report["completed_task_requests"] != len(ids) or not report["backend_api_token_counts_agree"]:
            raise GateError(f"historical API/backend timing mismatch: {run}")
        if not report["legacy_telemetry_coverage_ok"] or not report["resource_ok"]:
            raise GateError(f"historical resource/telemetry gap: {run}")
        old_grade = read(f"{run}-{'grade02' if run.startswith('task20') else 'grade'}.json")
        host_grade = read(f"c2-host-{run}-grade.json")
        old_statuses = [(x["task_id"], x["status"]) for x in old_grade["scores"]]
        host_statuses = [(x["task_id"], x["status"]) for x in host_grade["scores"]]
        if old_statuses != host_statuses or [x[0] for x in host_statuses] != ids:
            raise GateError(f"historical automatic grading changed: {run}")
        judgment = read(f"{run}-judgment.json")
        if [x["task_id"] for x in judgment["rows"]] != ids:
            raise GateError(f"historical judgment IDs changed: {run}")
        if judgment["pass_count"] != sum(x["status"] == "PASS" for x in judgment["rows"]):
            raise GateError(f"historical pass count inconsistent: {run}")
        server[run] = {"legacy_frozen_m5_after_gate_repair": report["m5_secondary_frozen_criterion_met"],
                       "legacy_telemetry_complete": True,
                       "api_backend_counts_agree": True,
                       "decode_tok_s": report["aggregate_decode_tok_s"],
                       "judgment_pass": judgment["pass_count"],
                       "automatic_grade_matches_original_on_host": True,
                       "c2_new_schema_qualified": False,
                       "c2_new_schema_limit": "historical samples lack PID per sample and memory.peak; schema cannot be backfilled"}
    old_ab = read("m3-capacity32-ab-summary.json")
    new_ab = read("c2-legacy-m3-capacity32-reaudit.json")
    if old_ab["run_order"] != new_ab["run_order"] or old_ab["summary"] != new_ab["summary"] or \
       not new_ab["all_same_response_hashes"] or not new_ab["all_resource_and_exit_ok"]:
        raise GateError("historical 24/32 A/B changed or lacks telemetry")
    paired = read("m6-paired-summary.json")
    if paired["score"].get("stock20b") != 8 or paired["score"].get("target120b") != 8 or \
       paired["score"].get("denominator") != 10:
        raise GateError("historical paired score changed")
    report = {
        "schema_version": "c2-legacy-reaudit-index-v1",
        "parent_campaign": "tesy-scale-lab-20260926",
        "analyzer_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "analyzer_scripts_sha256": {name: digest(ROOT / "tools" / name) for name in
                                    ("analyze_task_run.py", "summarize_slot_ab.py", "grade_tasks.py",
                                     "c2_reaudit_index.py")},
        "source_sha256_at_reaudit": hashes,
        "server": server,
        "m3_capacity32": {"status": "LEGACY_REAUDITED_LIMITED", "summary": new_ab["summary"],
                          "sustained32": "NOT_RUN"},
        "m6": {"status": "LEGACY_JUDGMENT_CONSISTENT", "stock20b_pass": 8,
               "target120b_pass": 8, "limitations": "saved manual judgments checked for internal consistency, not independently readjudicated"},
        "limits": ["source hashes show present files, not guaranteed historical file bytes",
                   "legacy samples have no PID per row or cgroup memory.peak; not C2-run-v1",
                   "no historical claim or threshold is rewritten",
                   "sandbox bubblewrap rerun failed; host isolated rerun matched old automatic statuses"],
    }
    output = RESULTS / "c2-historical-reaudit-index.json"
    with output.open("x") as target:
        json.dump(report, target, indent=2, allow_nan=False)
        target.write("\n")
    print(json.dumps({"server": server, "m3": report["m3_capacity32"]["status"],
                      "m6": report["m6"]["status"]}))


if __name__ == "__main__":
    main()
