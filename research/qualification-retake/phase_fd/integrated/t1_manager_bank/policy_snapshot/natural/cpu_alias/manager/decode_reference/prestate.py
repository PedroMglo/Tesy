"""Bind the four weights in the setup recipe to the observed C270 state before decode."""

import argparse
import json
import os
import struct
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
m = run_path(HERE / "prepare.py")
need = m["need"]
REF = "8f9b7bb692c9974eac9bca2cb8a4d08436ef83a1e245ba2bbe37442430c6e10f"


def ranks(blob, n, nb):
    need(
        n > 0 and nb[0] == 4 and nb[1] >= 16 and len(blob) == (n - 1) * nb[1] + 16,
        "logical rank view",
    )
    tokens = [struct.unpack_from("<4i", blob, k * nb[1]) for k in range(n)]
    need(all(len(set(t)) == 4 and 0 <= min(t) <= max(t) < 128 for t in tokens), "rank")
    return tokens


def annotate(prior, records, last):
    old = {int(r["expert"]): r for r in prior}
    need(set(old) == set(m["IDS"]) and len(prior) == 4, "prestate coverage")
    result = []
    for r in records:
        e = r["expert"]
        row = old[e]
        state = row["class"]
        side = (int(row["slot"]), int(row["generation"]))
        if state == "READY":
            need(
                e in last and side == (r["capture_slot"], r["capture_generation"]),
                "READY lifetime or prior rank",
            )
        else:
            need(state == "ABSENT_RELOAD" and side == (-1, 0), "cold boundary")
        result.append(
            dict(
                expert=e,
                state_before=state,
                slot_before=side[0],
                generation_before=side[1],
                present_in_last_tile=e in last,
                consumer_slot=r["capture_slot"],
                consumer_generation=r["capture_generation"],
            )
        )
    return result


def run(a):
    ref = m["sealed"](a.prepared / "receipt.json", REF)
    plan = m["sealed"](a.prepared / "plan.json", ref["plan_sha256"])
    orig = a.lab / "results" / m["C270"]
    mani = m["sealed"](orig / "raw-manifest.json", ref["c270_manifest_sha256"])
    prefix = "results/" + m["C270"] + "/raw/c270-r0.capture/"
    rows = {r["path"][len(prefix) :]: r for r in mani["files"] if r["path"].startswith(prefix)}

    def read(name):
        r = rows[name]
        return m["read"](orig / "raw/c270-r0.capture" / name, r["sha256"], r["size"])

    pre = [
        r
        for r in m["table"](read("route_prestate.tsv"))
        if r["phase"] == "decode0" and r["layer"] == "0"
    ]
    (tile,) = [
        r
        for r in m["table"](read("index.tsv"))
        if r["phase"] == "prefill_final" and r["layer"] == "0" and r["name"] == "ffn_moe_topk"
    ]
    need(
        (
            tile["first_abs"],
            tile["state_tokens"],
            tile["ne"],
            tile["nb"],
            tile["type"],
            tile["chunk"],
        )
        == ("160", "29", "4,29,1,1", "4,512,14848,14848", "i32", "5"),
        "final prefill tile",
    )
    ts = ranks(read(tile["file"]), 29, (4, 512))
    members = set().union(*ts)
    states = annotate(pre, plan["records"], members)
    misses = sum(r["state_before"] != "READY" for r in states)
    return dict(
        status="PASS_C270_DECODE0_PRESTATE_JOIN",
        reference_sha256=REF,
        plan_sha256=ref["plan_sha256"],
        last_tile=dict(
            first=160,
            last=188,
            tokens=29,
            pitch_bytes=512,
            distinct=len(members),
            topk_file_sha256=rows[tile["file"]]["sha256"],
        ),
        prestate_sha256=rows["route_prestate.tsv"]["sha256"],
        ranks=states,
        demanded_new_experts=misses,
        conditional_pack_weight_read_bytes=misses * m["schema"]["WINDOW"],
        setup_four_entire_records_bytes=ref["planned_record_reads_bytes"],
        pack_reads=0,
        model_forwards=0,
        program_sha256=m["sha"](Path(__file__)),
        protocol_sha256=m["sha"](HERE / "prestate.md"),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("lab", "prepared", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a)
    except Exception as e:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}")
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2)
        f.write("\n")
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
