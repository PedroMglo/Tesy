#!/usr/bin/env python3
"""Compare logical target boundary with an already referenced no-preload capture."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from c2_gate import strict_json
from c3_compare_capture_logits import resources

PHASES = ("prefill0", "prefill128", "prefill_final", "decode0", "decode1", "decode7", "decode31")
STAGES = ("attn_post_norm", "ffn_moe_logits", "ffn_moe_probs", "ffn_moe_topk",
          "ffn_moe_weights_softmax", "ffn_moe_out")
VOCAB_BYTES = 201088 * 4


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def indexed(root):
    rows = list(csv.DictReader((root / "index.tsv").open(), delimiter="\t"))
    if not rows or (root / "phases.txt").read_text().splitlines() != list(PHASES):
        raise ValueError("index/phases absent or incomplete")
    selected = {}
    for row in rows:
        if set(row) != {"phase", "layer", "name", "type", "ne", "nb", "bytes", "file"}:
            raise ValueError("index schema changed")
        if row["name"] not in STAGES:
            continue
        key = (row["phase"], int(row["layer"]), row["name"])
        if key in selected or key[0] not in PHASES or not 0 <= key[1] < 36:
            raise ValueError("duplicate/invalid logical boundary row")
        file = root / row["file"]
        if file.parent != root or file.stat().st_size != int(row["bytes"]):
            raise ValueError("missing, escaped or incomplete tensor file")
        selected[key] = (row, file)
    expected = {(phase, layer, stage) for phase in PHASES for layer in range(36)
                for stage in STAGES}
    if set(selected) != expected:
        raise ValueError("logical boundary matrix incomplete")
    return selected


def check_bytes(root):
    rows = list(csv.DictReader((root / "byte_checks.tsv").open(), delimiter="\t"))
    if not rows or any(row.get("status") != "EQUAL" for row in rows):
        raise ValueError("direct slot-byte check absent or failed")
    layers = {int(row["layer"]) for row in rows}
    if layers != {0, 35} or any(int(row["bytes"]) <= 0 for row in rows):
        raise ValueError("direct slot-byte witness coverage changed")
    return len(rows)


def compare(case, candidate, baseline, bridge_binary, bridge_report):
    old = Path("results") / baseline
    new = Path("results") / candidate
    manifests = [strict_json(Path(str(stem)+".json").read_text()) for stem in (old, new)]
    for stem, manifest in zip((old, new), manifests):
        resources(manifest, Path(str(stem)+".samples.jsonl"))
    for key in ("model_id", "backend_sha", "workload_sha256", "backend_libraries_sha256"):
        if manifests[0][key] != manifests[1][key]:
            raise ValueError(f"candidate {key} changed")
    if manifests[0]["explicit_env"].get("LLAMA_MOE_STREAM_NO_PRELOAD") != "1":
        raise ValueError("baseline does not disable preload")
    if bridge_binary:
        if baseline != f"c3-r2-broad-{case}01" or \
           manifests[1]["explicit_env"].get("LLAMA_MOE_STREAM_NO_PRELOAD") != "1":
            raise ValueError("binary bridge must keep preload disabled")
    else:
        if manifests[0]["binary_sha256"] != manifests[1]["binary_sha256"] or \
           "LLAMA_MOE_STREAM_NO_PRELOAD" in manifests[1]["explicit_env"]:
            raise ValueError("preload arms/binary not identified")
    summary = Path(f"results/c3-r2-broad-{case}-reference-summary02.json")
    reference = strict_json(summary.read_text())
    if reference["status"] != "PASS" or reference["comparisons"] != 252 or \
       reference["capture_run_id"] != f"c3-r2-broad-{case}01":
        raise ValueError("independent baseline layer reference not PASS")
    original = Path("results") / reference["capture_run_id"]
    if reference["capture_manifest_sha256"] != sha(Path(str(original)+".json")) or \
       reference["capture_index_sha256"] != sha(Path(str(original)+".raw")/"index.tsv"):
        raise ValueError("independent reference source changed")
    if not bridge_binary and baseline != reference["capture_run_id"]:
        if bridge_report is None:
            raise ValueError("new baseline lacks qualified binary bridge")
        bridge = strict_json(bridge_report.read_text())
        if bridge.get("status") != "PASS" or bridge.get("candidate_run_id") != baseline or \
           bridge.get("baseline_run_id") != reference["capture_run_id"] or \
           bridge.get("independent_reference_summary_sha256") != sha(summary) or \
           bridge.get("source_sha256",{}).get(str(Path(str(old)+".json"))) != \
               sha(Path(str(old)+".json")):
            raise ValueError("binary bridge identity/status invalid")
    old_root, new_root = (Path(str(stem)+".raw") for stem in (old, new))
    old_rows, new_rows = indexed(old_root), indexed(new_root)
    equal = 0
    failures = []
    for key in sorted(old_rows):
        a, a_file = old_rows[key]
        b, b_file = new_rows[key]
        if any(a[field] != b[field] for field in ("type", "ne", "nb", "bytes")) or \
           a_file.read_bytes() != b_file.read_bytes():
            failures.append(key)
        else:
            equal += 1
    for phase in PHASES:
        left, right = (root / f"{phase}.logits.f32" for root in (old_root, new_root))
        if left.stat().st_size != VOCAB_BYTES or right.stat().st_size != VOCAB_BYTES or \
           left.read_bytes() != right.read_bytes():
            failures.append((phase, "full_logits"))
    checked = check_bytes(new_root)
    return {"schema":"c3-preload-capture-v1",
            "status":"PASS" if not failures else "FAIL_MISMATCH",
            "case":case,"baseline_run_id":baseline,"candidate_run_id":candidate,
            "mode":"BINARY_BRIDGE" if bridge_binary else "PRELOAD_COMPARE",
            "bridge_report_sha256":sha(bridge_report) if bridge_report else None,
            "independent_reference_summary_sha256":sha(summary),
            "logical_tensor_pairs":len(old_rows),"logical_tensor_bitwise_equal":equal,
            "full_logit_pairs":len(PHASES),"direct_candidate_slice_checks":checked,
            "failures":failures[:25],"failure_count":len(failures),
            "source_sha256":{str(path):sha(path) for path in
                             (Path(str(old)+".json"),Path(str(new)+".json"),
                              old_root/"index.tsv",new_root/"index.tsv",
                              new_root/"byte_checks.tsv")},
            "analyzer_sha256":sha(__file__)}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("case",choices=("log","spec"))
    ap.add_argument("candidate_run_id")
    ap.add_argument("--baseline-run-id")
    ap.add_argument("--bridge-binary",action="store_true")
    ap.add_argument("--bridge-report",type=Path)
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    try:
        result=compare(args.case,args.candidate_run_id,
                       args.baseline_run_id or f"c3-r2-broad-{args.case}01",
                       args.bridge_binary,args.bridge_report)
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
        result={"schema":"c3-preload-capture-v1","status":"FAIL_EVIDENCE",
                "case":args.case,"candidate_run_id":args.candidate_run_id,
                "reason":f"{type(exc).__name__}: {exc}"}
    with args.output.open("x") as out:
        json.dump(result,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({"status":result["status"],"pairs":result.get("logical_tensor_pairs"),
                      "equal":result.get("logical_tensor_bitwise_equal"),
                      "reason":result.get("reason"),"failures":result.get("failures")}))
    return 0 if result["status"]=="PASS" else 1


if __name__=="__main__":
    raise SystemExit(main())
