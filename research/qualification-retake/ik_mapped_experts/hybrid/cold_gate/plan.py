"""Freeze the first gate's ordered OFF transfers and independently hash the original ranges."""

import argparse
import hashlib
import json
import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
A = run_path(str(HERE.parent / "driver_62073/real_authority.py"))
need, sha, receipt = A["need"], A["sha"], A["receipt"]
PAIR = "97291f30c38c5f29fe9c5a6a08aaa3fd0d21b7132da486e2ca54a09244c1b502"
NAME = "blk.0.ffn_gate_exps.weight"
PAGE = 4096


def identity(st):
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def geometry(lines, start, size, name=NAME):
    rows = []
    cursor = scratch = 0
    for line in lines:
        v = line.split()
        if len(v) != 11 or v[:2] != ["SET", "3"] or v[5] != "moe_cache." + name:
            continue
        offset, dest, n = map(int, (v[10], v[7], v[8]))
        if not start <= offset < start + size:
            continue
        need(
            offset + n <= start + size and n > 0 and dest == cursor and v[4] == "async",
            "wrong source or slot run",
        )
        rows.append(dict(source=offset, dest=dest, bytes=n, scratch=scratch + offset % PAGE))
        scratch += (offset % PAGE + n + PAGE - 1) // PAGE * PAGE
        cursor += n
    need((len(rows), cursor, scratch) == (33, 215913600, 216051712), "gate geometry")
    return rows, cursor, scratch


def create(inputs, family):
    data = receipt(inputs / "receipt.json", A["INPUT"])
    plan = inputs / "plan.tsv"
    need(data["plan_sha256"] == sha(plan) == A["PLAN"], "tensor plan")
    root = receipt(family / "receipt.json", PAIR)
    arm = family / "OFF/BANK288"
    sub = receipt(arm / "receipt.json", root["arms"]["OFF/BANK288"]["receipt_sha256"])
    need(
        root["status"] == sub["status"] == "PASS_CALLBACK_OFF_TWO_CUTS"
        and A["FR"]["inventory"](arm) == sub["raw_sha256"],
        "OFF evidence",
    )
    model = Path(data["model"]).resolve(strict=True)
    inode = data["model_stat"]
    need(
        data["model_sha256"] == root["authority"]["model_sha256"] == A["stock"].MODEL_SHA
        and inode == root["authority"]["model_stat"] == identity(model.stat())
        and model.stat().st_uid == os.getuid(),
        "original internal GGUF",
    )
    start, size, _ = A["G"]["CAP"]["tensor_plan"](plan)[NAME]
    need((start, size) == (1838905376, 564019200), "gate tensor")
    rows, payload, scratch = geometry((arm / "raw/stdout").read_text().splitlines(), start, size)
    with model.open("rb", buffering=0) as f:
        need(identity(os.fstat(f.fileno())) == inode, "reference file")
        for row in rows:
            b = os.pread(f.fileno(), row["bytes"], row["source"])
            need(len(b) == row["bytes"], "short independent read")
            row["sha256"] = hashlib.sha256(b).hexdigest()
        need(identity(os.fstat(f.fileno())) == inode, "reference file drift")
    return dict(
        status="SEALED_GATE_BYTES",
        pair_sha256=PAIR,
        plan_sha256=A["PLAN"],
        stdout_sha256=sub["raw_sha256"]["raw/stdout"],
        model=str(model),
        model_sha256=data["model_sha256"],
        model_stat=inode,
        tensor_start=start,
        tensor_bytes=size,
        page_B=PAGE,
        payload_B=payload,
        scratch_B=scratch,
        sets=rows,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("inputs", "family", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        r = create(a.inputs, a.family)
    except Exception as exc:
        r = dict(status="FAIL_PRESERVED", reason=str(exc))
    (a.new_output_dir / "receipt.json").write_text(json.dumps(r, sort_keys=True, indent=2) + "\n")
    print(r["status"], r.get("reason", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
