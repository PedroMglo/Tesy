#!/usr/bin/env python3
"""Compare frozen seven-position callback OFF/ON target logits per case."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import struct

from c2_gate import GateError, strict_json
from c3_compare_capture_logits import BYTES_PER_ROW, VOCAB, resources


CASES = {"log":("log_medium",189,43,[("prefill0","prompt",31),
                                      ("prefill128","prompt",159),
                                      ("prefill_final","prompt",188),
                                      ("decode0","continuation",189),
                                      ("decode1","continuation",190),
                                      ("decode7","continuation",196),
                                      ("decode31","continuation",220)]),
         "spec":("spec_pressure",414,49,[("prefill0","prompt",31),
                                           ("prefill128","prompt",159),
                                           ("prefill_final","prompt",413),
                                           ("decode0","continuation",414),
                                           ("decode1","continuation",415),
                                           ("decode7","continuation",421),
                                           ("decode31","continuation",445)])}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(case):
    name,n_prompt,n_cont,selected=CASES[case]
    off_stem=Path(f"results/c3-r2-broad-parity-off-{case}01")
    on_stem=Path(f"results/c3-r2-broad-{case}01")
    off_manifest_path=Path(str(off_stem)+".json")
    on_manifest_path=Path(str(on_stem)+".json")
    off=strict_json(off_manifest_path.read_text())
    on=strict_json(on_manifest_path.read_text())
    for key in ("model_id","backend_sha","workload_sha256"):
        if off[key]!=on[key]:
            raise GateError(f"OFF/ON {key} differs")
    off_samples=resources(off,Path(str(off_stem)+".samples.jsonl"))
    on_samples=resources(on,Path(str(on_stem)+".samples.jsonl"))
    rows_path=Path(str(off_stem)+".rows.tsv")
    rows=list(csv.DictReader(rows_path.open(),delimiter="\t"))
    expected=[("prompt",min(start+31,n_prompt-1)) for start in range(0,n_prompt,32)]
    expected += [("continuation",n_prompt+i) for i in range(n_cont)]
    if len(rows)!=len(expected):
        raise GateError("OFF row count differs from frozen expectation")
    for i,(row,(phase,position)) in enumerate(zip(rows,expected)):
        if set(row)!={"case","phase","position","row"} or \
           row["case"]!=name or row["phase"]!=phase or \
           int(row["position"])!=position or int(row["row"])!=i:
            raise GateError(f"OFF row {i} identity/order differs")
    off_file=Path(str(off_stem)+".f32")
    if off_file.stat().st_size!=len(rows)*BYTES_PER_ROW:
        raise GateError("OFF float32 payload incomplete")
    on_root=Path(str(on_stem)+".raw")
    if (on_root/"phases.txt").read_text().splitlines()!=[x[0] for x in selected]:
        raise GateError("ON phase schedule incomplete")
    matches=[]
    with off_file.open("rb") as source:
        for phase,kind,position in selected:
            found=[int(row["row"]) for row in rows if row["phase"]==kind and
                   int(row["position"])==position]
            if len(found)!=1:
                raise GateError("selected OFF row missing/duplicated")
            source.seek(found[0]*BYTES_PER_ROW)
            left=source.read(BYTES_PER_ROW)
            right=(on_root/f"{phase}.logits.f32").read_bytes()
            if len(left)!=BYTES_PER_ROW or len(right)!=BYTES_PER_ROW:
                raise GateError("selected vector size differs")
            if not all(math.isfinite(x) for x in struct.unpack(f"<{VOCAB}f",left)) or \
               not all(math.isfinite(x) for x in struct.unpack(f"<{VOCAB}f",right)):
                raise GateError("nonfinite selected vector")
            matches.append({"phase":phase,"position":position,"off_row":found[0],
                            "bitwise_equal":left==right,
                            "off_sha256":hashlib.sha256(left).hexdigest(),
                            "on_sha256":hashlib.sha256(right).hexdigest()})
    return {"schema":"c3-broad-off-on-logits-v1","case":case,
            "status":"PASS" if all(m["bitwise_equal"] for m in matches) else "FAIL_MISMATCH",
            "off_run_id":off_stem.name,"on_run_id":on_stem.name,
            "expected_off_rows":len(expected),"selected_vectors":len(matches),
            "vocab":VOCAB,"sample_counts":[off_samples,on_samples],"rows":matches,
            "source_sha256":{str(path):digest(path) for path in
                (off_manifest_path,on_manifest_path,rows_path,off_file,on_root/"index.tsv")},
            "analyzer_sha256":digest(__file__)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("case",choices=CASES)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    try:
        result=compare(args.case)
    except (GateError,KeyError,ValueError,TypeError,OSError,struct.error) as exc:
        result={"schema":"c3-broad-off-on-logits-v1","case":args.case,
                "status":"FAIL_EVIDENCE","reason":f"{type(exc).__name__}: {exc}"}
    with args.output.open("x") as out:
        json.dump(result,out,indent=2,allow_nan=False);out.write("\n")
    print(json.dumps({"status":result["status"],"case":args.case,
                      "rows":len(result.get("rows",[])),"reason":result.get("reason")}))
    return 0 if result["status"]=="PASS" else 1


if __name__=="__main__":
    raise SystemExit(main())
