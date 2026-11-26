"""Reopen the ON logs using only transport evidence and bound single-read block rounding."""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
OFF = run_path(str(HERE / "grade.py"))
T, G, R, need = (OFF[k] for k in ("T", "G", "R", "need"))
BLOCKS = (4096, 128 * 1024, 2 * 1024 * 1024)


def aligned(offset, size, block):
    need(offset >= 0 and size > 0 and block > 0, "positive file range")
    return ((offset + size + block - 1) // block - offset // block) * block


def study(lines, scope, control):
    owners, copies = {}, defaultdict(list)
    for line in lines:
        fields = line.split()
        if len(fields) < 2 or fields[1] not in ("3", "4"):
            continue
        if fields[0] == "SET" and T["BANK_NAME"].fullmatch(fields[5]):
            owners[fields[2]] = int(fields[1])
        if fields[0] == "COPY" and fields[2] in owners:
            phase = owners[fields[2]]
            need(phase == int(fields[1]) and fields[4] == "1" and fields[9] == "0", "matrix copy")
            copies[phase].append((int(fields[8]), int(fields[7])))
    phases = {}
    for name, phase in T["PHASE"].items():
        chunks = copies[phase]
        payload = sum(n for _, n in chunks)
        reads = scope[name]["scope_nvme_read_B"]
        need(payload == control["matrix_requests_B"][name] and chunks, "verified matrix bytes")
        # Count even repeated/overlapping blocks in full for each COPY. The scenario
        # permits one cold read of each aligned span, with no sharing whatsoever.
        rounded = {b: sum(aligned(start, n, b) for start, n in chunks) for b in BLOCKS}
        phases[name] = dict(
            matrix_copy_calls=len(chunks),
            payload_B=payload,
            scope_nvme_read_B=reads,
            sum_single_cold_read_B=rounded,
            scope_read_B_beyond_scenario={b: max(0, reads - n) for b, n in rounded.items()},
        )
    return phases


def run(family, plan):
    grades = OFF["reference"](family, plan)
    tensors = G["CAP"]["tensor_plan"](plan)
    result = {}
    for mode, g in grades.items():
        p = family / mode
        arm = json.loads((p / "receipt.json").read_bytes())
        lines = (p / "raw/stdout").read_text().splitlines()
        control = T["compare"](lines, tensors, g["slots"], g["ledger"])
        need(control["match"], "ON graph witness disagrees with passive transport")
        scope = R["by_phase"](p / "raw/monitor.jsonl", arm)
        result[mode] = dict(transport=control, single_read=study(lines, scope, control))
    return dict(
        status="REPRODUCED_ON_TRANSPORT",
        original_sha256=R["ROOT_SHA"],
        model_starts=0,
        callback_off_physical="NOT_RUN",
        arms=result,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("family", "plan", "new-output-dir"):
        parser.add_argument("--" + key, type=Path, required=True)
    a = parser.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a.family, a.plan)
    except Exception as exc:
        result = {"status": "FAIL_PRESERVED", "reason": str(exc)}
    with (a.new_output_dir / "review.json").open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    print(result["status"], result.get("reason", ""))
    raise SystemExit(result["status"] == "FAIL_PRESERVED")
