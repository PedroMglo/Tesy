"""Authenticate all three banks of the first physical OFF288 prefill layer in journal order."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
P = run_path(str(HERE / "plan.py"))
G = run_path(str(HERE / "grade.py"))
need = P["need"]
ROLES = ("gate", "up", "down")


def create(inputs, family, gate):
    need(P["sha"](gate) == G["REFERENCE"], "single gate reference")
    base = P["create"](inputs, family)
    need(base == json.loads(gate.read_bytes()), "independent gate reference mismatch")
    tensor_plan = P["A"]["G"]["CAP"]["tensor_plan"](inputs / "plan.tsv")
    lines = (family / "OFF/BANK288/raw/stdout").read_text().splitlines()
    sets, tensors = [], {}
    scratch = 0
    with open(base["model"], "rb", buffering=0) as f:
        for role in ROLES:
            name = "blk.0.ffn_" + role + "_exps.weight"
            off, n, _ = tensor_plan[name]
            rows, payload, owned = P["geometry"](lines, off, n, name)
            tensors[role] = dict(start=off, bytes=n, payload_B=payload)
            for row in rows:
                data = os.pread(f.fileno(), row["bytes"], row["source"])
                need(len(data) == row["bytes"], "short independent layer read")
                row.update(
                    role=role,
                    scratch=scratch + row["scratch"],
                    sha256=hashlib.sha256(data).hexdigest(),
                )
                sets.append(row)
            scratch += owned
        need(P["identity"](os.fstat(f.fileno())) == base["model_stat"], "source drift")
    order = []
    for line in lines:
        v = line.split()
        if len(v) != 11 or v[:2] != ["SET", "3"] or not v[5].startswith("moe_cache."):
            continue
        offset = int(v[10])
        for role, t in tensors.items():
            if t["start"] <= offset < t["start"] + t["bytes"]:
                need(v[5] == f"moe_cache.blk.0.ffn_{role}_exps.weight", "target role")
                order.append((role, offset, int(v[7]), int(v[8])))
    need(
        order == [(r["role"], r["source"], r["dest"], r["bytes"]) for r in sets],
        "three-bank replay changes physical order",
    )
    need([r["sha256"] for r in sets[:33]] == [r["sha256"] for r in base["sets"]], "gate bytes")
    need(
        len(sets) == 99 and scratch == 648155136 and sum(r["bytes"] for r in sets) == 647740800,
        "three roles or scratch",
    )
    return {
        **{k: v for k, v in base.items() if k not in ("tensor_start", "tensor_bytes")},
        "status": "SEALED_LAYER_BYTES",
        "tensors": tensors,
        "sets": sets,
        "scratch_B": scratch,
        "payload_B": 647740800,
        "gate_reference_sha256": G["REFERENCE"],
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("inputs", "family", "gate", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        r = create(a.inputs, a.family, a.gate)
    except Exception as exc:
        r = dict(status="FAIL_PRESERVED", reason=str(exc))
    (a.new_output_dir / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    print(r["status"], r.get("reason", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
