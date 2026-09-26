#!/usr/bin/env python3
"""Fail-closed fixed-position OFF/ON logits comparison for the C3 prototype."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import struct

from c2_gate import GateError, strict_json


VOCAB = 201088
BYTES_PER_ROW = VOCAB * 4
POSITIONS = (("prompt", 31, "prefill0.logits.f32"),
             ("continuation", 189, "decode0.logits.f32"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resources(manifest, samples_path):
    if manifest.get("returncode") != 0 or manifest.get("stop_reason") is not None:
        raise GateError("run did not complete")
    start, end = manifest.get("cgroup_start"), manifest.get("cgroup_end")
    if not start or not end or start["path"] != end["path"] or \
       start["memory_max"] != 18*2**30 or end["memory_max"] != 18*2**30 or \
       start["swap_max"] != 0 or end["swap_max"] != 0 or end["swap_current"] != 0 or \
       end["memory_peak"] > end["memory_max"]:
        raise GateError("cgroup envelope/end state invalid")
    for group in ("events", "events_local"):
        for event in ("max", "oom", "oom_kill"):
            if start[group].get(event) != end[group].get(event):
                raise GateError("cgroup event changed")
    samples = [strict_json(line) for line in samples_path.read_text().splitlines()]
    if len(samples) < 2 or samples[0]["elapsed_s"] > 2 or \
       manifest["elapsed_s"] - samples[-1]["elapsed_s"] > 3:
        raise GateError("telemetry does not cover run")
    if any(b["elapsed_s"] <= a["elapsed_s"] or b["elapsed_s"]-a["elapsed_s"] > 3
           for a,b in zip(samples,samples[1:])):
        raise GateError("telemetry nonmonotone or gap")
    if any(s["proc"].get("VmSwap") != 0 or s["cgroup"].get("swap_current") != 0 or
           s["gpu"]["used_mib"] > 7000 or s["proc"].get("VmRSS",0) > 17*2**30 or
           s["mem_available_bytes"] < 6*2**30 or
           s["thermal"]["cpu_tctl_c"] > 95 or s["gpu"]["temperature_c"] > 80 or
           s["thermal"]["nvme_composite_c"] > 70 for s in samples):
        raise GateError("sampled resource guard violated")
    return len(samples)


def compare(off_stem, on_stem):
    off_manifest = strict_json(Path(str(off_stem)+".json").read_text())
    on_manifest = strict_json(Path(str(on_stem)+".json").read_text())
    if off_manifest["model_id"] != on_manifest["model_id"] or \
       off_manifest["backend_sha"] != on_manifest["backend_sha"] or \
       off_manifest["workload_sha256"] != on_manifest["workload_sha256"]:
        raise GateError("model/backend/workload identities differ")
    sample_counts = [resources(manifest, Path(str(stem)+".samples.jsonl"))
                     for stem,manifest in ((off_stem,off_manifest),(on_stem,on_manifest))]
    rows_path = Path(str(off_stem)+".rows.tsv")
    rows = list(csv.DictReader(rows_path.open(), delimiter="\t"))
    if len(rows) != 49 or any(set(r) != {"case","phase","position","row"} for r in rows) or \
       any(r["case"] != "log_medium" or int(r["row"]) != i for i,r in enumerate(rows)):
        raise GateError("OFF row index incomplete or reordered")
    off_data = Path(str(off_stem)+".f32")
    if off_data.stat().st_size != len(rows)*BYTES_PER_ROW:
        raise GateError("OFF logits payload incomplete")
    matches = []
    with off_data.open("rb") as source:
        for phase, position, on_name in POSITIONS:
            found = [r for r in rows if r["phase"] == phase and int(r["position"]) == position]
            if len(found) != 1:
                raise GateError("fixed OFF position missing/duplicated")
            row = int(found[0]["row"])
            source.seek(row*BYTES_PER_ROW)
            off_bytes = source.read(BYTES_PER_ROW)
            on_file = Path(str(on_stem)+".raw") / on_name
            on_bytes = on_file.read_bytes()
            if len(off_bytes) != BYTES_PER_ROW or len(on_bytes) != BYTES_PER_ROW:
                raise GateError("fixed logits row short")
            if any(not math.isfinite(x) for x in struct.unpack(f"<{VOCAB}f",off_bytes)) or \
               any(not math.isfinite(x) for x in struct.unpack(f"<{VOCAB}f",on_bytes)):
                raise GateError("nonfinite logits")
            matches.append({"phase":phase,"position":position,"off_row":row,
                            "bitwise_equal":off_bytes == on_bytes,
                            "off_sha256":hashlib.sha256(off_bytes).hexdigest(),
                            "on_sha256":hashlib.sha256(on_bytes).hexdigest()})
    return {"schema":"c3-off-on-logits-v1", "status":"PASS" if all(x["bitwise_equal"] for x in matches) else "FAIL_MISMATCH",
            "off_run_id":off_stem.name,"on_run_id":on_stem.name,
            "float32_vocab":VOCAB,"rows":matches,"sample_counts":sample_counts,
            "source_sha256":{str(path):digest(path) for path in
                             (Path(str(off_stem)+".json"),Path(str(on_stem)+".json"),
                              rows_path,off_data,Path(str(on_stem)+".raw/index.tsv"))}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("off_stem", type=Path)
    parser.add_argument("on_stem", type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args = parser.parse_args()
    try:
        report = compare(args.off_stem,args.on_stem)
    except (GateError, ValueError, KeyError, OSError, TypeError) as exc:
        report = {"schema":"c3-off-on-logits-v1","status":"FAIL_EVIDENCE",
                  "reason":f"{type(exc).__name__}: {exc}"}
    with args.output.open("x") as out:
        json.dump(report,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({"status":report["status"],"reason":report.get("reason"),
                      "rows":report.get("rows")},allow_nan=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
