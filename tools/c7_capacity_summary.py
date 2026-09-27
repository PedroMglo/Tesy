#!/usr/bin/env python3
"""Validate and compact the prospective C7 minimum-forward admission."""

import csv
import hashlib
import json
import math
import struct
from pathlib import Path

from c2_gate import GateError, strict_json
from c3_compare_capture_logits import resources


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("measurement_commit")
    args = p.parse_args()
    stem = args.root / "raw" / "c7-cap-p12-forward01"
    manifest_path = Path(str(stem) + ".json")
    manifest = strict_json(manifest_path.read_text())
    if manifest["run_id"] != stem.name or manifest["variant"] != "P12-forward-capacity":
        raise GateError("wrong capacity run identity")
    n_samples = resources(manifest, Path(str(stem) + ".samples.jsonl"))
    if manifest["artifact_identity"]["stat_at_launch"] != manifest["artifact_identity"]["stat_at_end"] or \
       manifest["mapped_backend_libraries_sha256"] != manifest["backend_libraries_sha256"] or \
       not manifest["mapped_libraries_match_ldd"]:
        raise GateError("model or mapped library identity mismatch")
    for suffix, expected in manifest["output_sha256"].items():
        if sha(Path(str(stem) + suffix)) != expected:
            raise GateError("raw manifest hash mismatch: " + suffix)
    logits = Path(str(stem) + ".f32")
    data = logits.read_bytes()
    if len(data) != 201088 * 4 or not all(math.isfinite(x) for (x,) in struct.iter_unpack("<f", data)):
        raise GateError("incomplete or nonfinite capacity logits")
    with Path(str(stem) + ".rows.tsv").open() as source:
        rows = list(csv.DictReader(source, delimiter="\t"))
    with (args.root.parent / "c3-p1-latency-ids01.tsv").open() as source:
        short_line = source.readline().rstrip("\n")
    case_name, short_ids = short_line.split("\t")
    prompt_ids = short_ids.split(",")
    if case_name != "latency-short" or len(prompt_ids) != 113:
        raise GateError("frozen short input changed")
    if len(rows) != 1 or set(rows[0]) != {"phase", "position", "row", "token_id"} or \
       rows[0]["phase"] != "prefill" or rows[0]["position"] != "112" or \
       rows[0]["row"] != "0" or rows[0]["token_id"] != prompt_ids[-1]:
        raise GateError("capacity output row invalid")
    with Path(str(stem) + ".ops.tsv").open() as source:
        ops = list(csv.DictReader(source, delimiter="\t"))
    if len(ops) != 1 or any(ops[0].get(k) != v for k, v in {
        "ngl": "12", "case": "latency-short", "init_only": "0",
        "no_teacher": "1", "output_rows": "1"}.items()):
        raise GateError("capacity operation index invalid")
    m = manifest["maxima"]
    cgroup_peak = manifest["cgroup_end"]["memory_peak"]
    admitted = (m["gpu_used_mib"] <= 6500 and cgroup_peak <= 16.5 * 2**30 and
                m["rss_bytes"] <= 16 * 2**30 and m["swap_bytes"] == 0 and
                manifest["cgroup_end"]["swap_current"] == 0)
    result = {
        "schema": "c7-forward-capacity-result-v1", "run_id": manifest["run_id"],
        "measurement_commit": args.measurement_commit,
        "protocol_sha256": sha(args.root / "capacity-protocol.json"),
        "raw_manifest_sha256": sha(manifest_path),
        "raw_stem": str(stem), "status": "CAPACITY_ADMITTED" if admitted else "CAPACITY_NOT_ADMITTED",
        "samples": n_samples, "elapsed_s_diagnostic_only": manifest["elapsed_s"],
        "resource_maxima": m, "cgroup_peak_bytes": cgroup_peak,
        "logits_count": 201088, "logits_sha256": sha(logits),
        "index_sha256": sha(Path(str(stem) + ".rows.tsv")),
        "ops_sha256": sha(Path(str(stem) + ".ops.tsv")),
        "model_stat_unchanged": True, "mapped_libraries_verified": True,
        "limits": {"gpu_total_mib": 6500, "cgroup_peak_bytes": int(16.5*2**30),
                   "rss_bytes": 16*2**30},
        "claim_limit": "one P12 113-ID prefill under E18; no fidelity, repeatability, timing or long-workload claim",
        "next_gate": "G2 same-profile OFF/ON and canonical routed-layer reference" if admitted else
                     "new identity and mechanism after capacity failure",
    }
    with (args.root / "capacity-summary.json").open("x") as out:
        json.dump(result, out, indent=2, sort_keys=True)
        out.write("\n")
    with (args.root / "runs.jsonl").open("a") as out:
        out.write(json.dumps({k: result[k] for k in (
            "run_id", "measurement_commit", "raw_manifest_sha256", "raw_stem",
            "status", "samples", "resource_maxima", "logits_sha256")}, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
