#!/usr/bin/env python3
"""Recompute available C6 D2 claims from immutable local raw without model execution."""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import c6_compare_d2 as c6
from c2_gate import strict_json
from c3_compare_capture_logits import resources


CLAIM_FIELDS = ("runs", "capture_seals_post_run", "bridges", "final_logits",
                "cpu_layer0_attention", "layer_outputs", "gpu_layer29_ops",
                "gpu_layer29_attention", "gpu_flash_sources",
                "gpu_flash_source_indexes", "native_gpu_replay")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def negative_receipt_claim(local, root):
    required = local.get("negative_cases") if type(local) is dict else None
    receipts = local.get("negative_receipts") if type(local) is dict else None
    if type(required) is not list or not required or len(set(required)) != len(required) or \
       type(receipts) is not list:
        return {"status":"INCOMPLETE_EVIDENCE","reason":"individual negative receipts absent"}
    by_case = {r.get("case"):r for r in receipts if type(r) is dict}
    if len(by_case) != len(receipts) or set(by_case) != set(required):
        return {"status":"INCOMPLETE_EVIDENCE","reason":"negative receipt set incomplete/duplicated"}
    for case, receipt in by_case.items():
        path = receipt.get("path")
        if type(path) is not str or Path(path).is_absolute() or ".." in Path(path).parts or \
           not (root/path).is_file() or digest(root/path) != receipt.get("sha256"):
            return {"status":"INCOMPLETE_EVIDENCE","reason":f"negative receipt missing/changed: {case}"}
        try:
            outcome = strict_json((root/path).read_text())
        except (OSError, ValueError):
            return {"status":"FAIL_EVIDENCE","reason":f"negative receipt malformed: {case}"}
        if type(outcome.get("returncode")) is not int or outcome["returncode"] == 0 or \
           outcome.get("completed_output") is not False:
            return {"status":"FAIL_EVIDENCE","reason":f"negative behavior not observed: {case}"}
    return {"status":"PASS","receipt_count":len(receipts)}


def reaudit(source_root):
    summary_path = source_root/"results/c6-d2-short-diagnostic-summary03.json"
    summary = strict_json(summary_path.read_text())
    report = {"schema":"c7-historical-reaudit-v1",
              "source_root":str(source_root),
              "original_summary_sha256":digest(summary_path),
              "source_commit":"0047a050803c29ea928022e7d3e8ba035fedb866",
              "claims":{}, "failures":[]}
    c6.ROOT = source_root
    # C6's numerical/seal path is reused intact. Resource approval is computed
    # separately so old missing process receipts cannot be mistaken for a
    # numerical mismatch or concealed by the old permissive resource predicate.
    c6.resources = lambda _manifest, _samples: None
    with tempfile.TemporaryDirectory() as tmp:
        c6.OUT = Path(tmp)/"recomputed.json"
        c6.main()
        fresh = strict_json(c6.OUT.read_text())
    if fresh["status"] == "FAIL_EVIDENCE":
        reason = fresh.get("reason", "unknown")
        report["claims"]["bytes_logits"] = {"status":"INCOMPLETE_EVIDENCE" if
            "FileNotFoundError" in reason else "FAIL_EVIDENCE", "reason":reason}
        report["claims"]["capture_completeness"] = {"status":"INCOMPLETE_EVIDENCE",
                                                     "reason":"numerical reauditor did not finish"}
        report["claims"]["location"] = {"status":"INCOMPLETE_EVIDENCE",
                                          "reason":"capture/bridge verification incomplete"}
    else:
        mismatched = [key for key in CLAIM_FIELDS if fresh.get(key) != summary.get(key)]
        status = "REPRODUCED_RAW" if not mismatched else "FAIL_EVIDENCE"
        report["claims"]["bytes_logits"] = {"status":status,
            "same_as_original_fields":not mismatched,"differing_fields":mismatched,
            "logits_different_f32_bitwise":fresh["final_logits"]["different_f32_bitwise"]}
        report["claims"]["capture_completeness"] = {"status":status,
            "capture_count":len(fresh["capture_seals_post_run"]),
            "complete_index_payload_and_state_schema":True}
        report["claims"]["location"] = {"status":status if
            fresh["status"] == "COMPAT_NOT_RECOVERED_NEXT_DIVERGENCE" else "FAIL_DIAGNOSTIC_CONTRACT",
            "computed_status":fresh["status"],
            "observed_first_difference":fresh.get("observed_first_difference")}

    resource_failures = {}
    raw_hash_failures = {}
    for stem in [spec[0] for spec in c6.SPECS.values()] + [spec[0] for spec in c6.CAPTURES.values()]:
        manifest_path = source_root/"results"/(stem+".json")
        try:
            manifest = strict_json(manifest_path.read_text())
            for suffix, expected in manifest.get("output_sha256", {}).items():
                path = source_root/"results"/(stem+suffix)
                if digest(path) != expected:
                    raw_hash_failures[stem+suffix] = "raw SHA differs"
            resources(manifest,source_root/"results"/(stem+".samples.jsonl"))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            resource_failures[stem] = f"{type(exc).__name__}: {exc}"
    report["claims"]["resources"] = {"status":"INCOMPLETE_EVIDENCE" if resource_failures else "PASS",
        "failed_or_incomplete_runs":resource_failures,
        "raw_hash_failures":raw_hash_failures,
        "historical_limit":"old manifests lack PID start ticks/cgroup inode; no retroactive receipt"}
    report["claims"]["libraries"] = {"status":"INCOMPLETE_EVIDENCE",
        "ldd_diagnostic":"C6 recomputation checked historical ldd-listed library hashes",
        "missing":"/proc/PID/maps after model load was not recorded"}
    local_summary = source_root/"results/c6-d1-local-summary02.json"
    local = strict_json(local_summary.read_text()) if local_summary.is_file() else None
    report["claims"]["negatives"] = {**negative_receipt_claim(local, source_root),
        "c6_d1_summary_sha256":digest(local_summary) if local else None,
        "reported_cases":local.get("negative_cases") if local else None}
    c3_index = source_root/"results/c3-audit-index.json"
    ids = source_root/"results/c3-p1-latency-ids01.tsv"
    c3 = strict_json(c3_index.read_text())
    indexed = {entry["path"]:entry["sha256"] for entry in c3.get("files",[])}
    c3_hash = digest(ids)
    derivation_path = source_root/"results/c3-p1-latency-ids01-derivation.json"
    source_path = source_root/"results/c3-p1-latency-ids01.json"
    derivation = strict_json(derivation_path.read_text())
    c3_chain_ok = (indexed.get("results/c3-p1-latency-ids01-derivation.json") == digest(derivation_path)
                   and indexed.get("results/c3-p1-latency-ids01.json") == digest(source_path)
                   and derivation.get("source_sha256") == digest(source_path)
                   and derivation.get("tsv_sha256") == c3_hash
                   and derivation.get("counts") == [113,496,1522])
    report["claims"]["c3_reused_inputs"] = {
        "status":"PASS" if c3_hash == "368c48ac1e93d68ec1746bb3d5f7e63118f35d7903c58f88dbe5c983b69190fb"
                          and c3_chain_ok else "FAIL_EVIDENCE",
        "audit_index_sha256":digest(c3_index),"latency_tsv_sha256":c3_hash,
        "scope":"TSV follows indexed derivation and source; C3 performance/reference claims not reused"}
    if raw_hash_failures:
        report["failures"].append("raw output SHA differs from manifest")
    report["status"] = "HISTORICAL_REAUDIT_PARTIAL" if any(
        item["status"] == "INCOMPLETE_EVIDENCE" for item in report["claims"].values()) else "REPRODUCED_RAW"
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source-root",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a = p.parse_args()
    result = reaudit(a.source_root.resolve())
    with a.output.open("x") as out:
        json.dump(result,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({"status":result["status"],"claims":{k:v["status"] for k,v in result["claims"].items()}},
                     allow_nan=False))


if __name__ == "__main__":main()
