#!/usr/bin/env python3
"""Fail-closed fixed-position OFF/ON logits comparison for the C3 prototype."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import struct

from c2_gate import GateError, number, strict_json


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
    identity = manifest.get("process_identity")
    if not isinstance(identity, dict) or type(identity.get("pid")) is not int or \
       type(identity.get("start_ticks")) is not int or \
       type(identity.get("cgroup_inode")) is not int or \
       not all(identity[k] > 0 for k in ("pid", "start_ticks", "cgroup_inode")) or \
       not isinstance(identity.get("cgroup_path"), str) or \
       not identity["cgroup_path"].startswith("/"):
        raise GateError("process launch identity missing/invalid")
    if not isinstance(start, dict) or not isinstance(end, dict) or \
       start.get("path") != end.get("path") or start.get("path") != identity["cgroup_path"] or \
       start.get("memory_max") != 18*2**30 or end.get("memory_max") != 18*2**30 or \
       start.get("swap_max") != 0 or end.get("swap_max") != 0:
        raise GateError("cgroup envelope/end state invalid")
    for name in ("memory_peak", "memory_current", "swap_current"):
        number(end.get(name), f"end {name}", minimum=0, integer=True)
    if end["swap_current"] != 0 or end["memory_peak"] > end["memory_max"]:
        raise GateError("end memory/swap guard violated")
    for group in ("events", "events_local"):
        if type(start.get(group)) is not dict or type(end.get(group)) is not dict:
            raise GateError("cgroup event group missing")
        for event in ("max", "oom", "oom_kill"):
            number(start[group].get(event), f"start {group}.{event}", minimum=0, integer=True)
            number(end[group].get(event), f"end {group}.{event}", minimum=0, integer=True)
            if start[group].get(event) != end[group].get(event):
                raise GateError("cgroup event changed")
    samples = [strict_json(line) for line in samples_path.read_text().splitlines()]
    elapsed = number(manifest.get("elapsed_s"), "run elapsed", positive=True)
    # elapsed is rounded to milliseconds by run_bounded. A 50 ms end tolerance
    # covers that rounding and collection scheduling, not a post-exit sample.
    terminal_tolerance_s = 0.05
    if len(samples) < 2 or number(samples[0].get("elapsed_s"), "first sample time", minimum=0) > 2 or \
       elapsed - number(samples[-1].get("elapsed_s"), "last sample time", minimum=0) > 3:
        raise GateError("telemetry does not cover run")
    previous_t = -1.0
    previous_peak = 0
    for i, s in enumerate(samples):
        t = number(s.get("elapsed_s"), f"sample {i} time", minimum=0)
        if t <= previous_t or t-previous_t > 3 and previous_t >= 0 or t > elapsed+terminal_tolerance_s:
            raise GateError("telemetry nonmonotone/gap/post-terminal")
        previous_t = t
        if s.get("pid") != identity["pid"] or s.get("process_identity") != identity:
            raise GateError("sample PID/start ticks/cgroup identity changed")
        cg, proc, gpu, thermal = (s.get(k) for k in ("cgroup", "proc", "gpu", "thermal"))
        if not all(type(x) is dict for x in (cg, proc, gpu, thermal)) or \
           cg.get("path") != identity["cgroup_path"] or cg.get("memory_max") != 18*2**30 or \
           cg.get("swap_max") != 0:
            raise GateError("sample cgroup/telemetry missing or changed")
        for name in ("VmRSS", "VmSwap", "VmHWM"):
            number(proc.get(name), f"sample {i} {name}", minimum=0, integer=True)
        for name in ("memory_current", "memory_peak", "swap_current"):
            number(cg.get(name), f"sample {i} {name}", minimum=0, integer=True)
        for name in ("used_mib", "temperature_c"):
            number(gpu.get(name), f"sample {i} GPU {name}", minimum=0)
        for name in ("cpu_tctl_c", "nvme_composite_c"):
            number(thermal.get(name), f"sample {i} thermal {name}", minimum=0)
        number(s.get("mem_available_bytes"), f"sample {i} MemAvailable", minimum=0, integer=True)
        if cg["memory_peak"] < max(previous_peak, cg["memory_current"]):
            raise GateError("cgroup peak inconsistent")
        previous_peak = cg["memory_peak"]
        for group in ("events", "events_local"):
            if type(cg.get(group)) is not dict:
                raise GateError("sample events missing")
            for event in ("max", "oom", "oom_kill"):
                number(cg[group].get(event), f"sample {i} {group}.{event}", minimum=0, integer=True)
                if cg[group][event] != start[group][event]:
                    raise GateError("sample cgroup event changed")
        if proc["VmSwap"] or cg["swap_current"] or cg["memory_current"] > 18*2**30 or \
           cg["memory_peak"] > 18*2**30 or gpu["used_mib"] > 7000 or \
           proc["VmRSS"] > 17*2**30 or s["mem_available_bytes"] < 6*2**30 or \
           thermal["cpu_tctl_c"] > 95 or gpu["temperature_c"] > 80 or \
           thermal["nvme_composite_c"] > 70:
            raise GateError("sampled resource guard violated")
    if type(manifest.get("output_sha256")) is not dict or \
       manifest["output_sha256"].get(".samples.jsonl") != digest(samples_path):
        raise GateError("sample raw hash differs from manifest")
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
