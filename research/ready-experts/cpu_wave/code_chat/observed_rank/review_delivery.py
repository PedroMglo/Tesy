"""Reconcile the compact quartet result with the service ledger and optional archived journals."""

import argparse
import json
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent
Q = run_path(HERE / "quartet.py")
read, need, sha = (Q[k] for k in ("read", "need", "file_sha"))


def verify(archive=None):
    s = read(HERE / "stripe-result.json")
    r = read(HERE / "quartet-result.json")
    cmds = read(HERE / "quartet-commands.json")
    need(
        sha(HERE / "stripe-result.json") == read(HERE / "stripe-commands.json")["decision_sha256"]
        and sha(HERE / "quartet-result.json") == cmds["receipt_sha256"]
        and all(s[k] == r[k] for k in ("model_sha256", "pack_sha256", "index_sha256")),
        "frozen results",
    )
    for row, file, method in (
        (s, "stripe.py", "stripe-protocol.md"),
        (r, "quartet.py", "quartet-protocol.md"),
    ):
        need(
            row["program_sha256"] == sha(HERE / file)
            and row["protocol_sha256"] == sha(HERE / method),
            "frozen code",
        )
    for name, values in s["arms"].items():
        spans = values["spans"]
        flat = [p for lo, hi in spans for p in range(lo, hi, s["page_bytes"])]
        need(
            len(set(flat)) == len(flat) and sorted(flat) == list(range(0, 13221888, 4096)),
            "complete page set",
        )
        n = values["completions_before_compute"]
        need(
            sum(hi - lo for lo, hi in spans[:n])
            == values["bytes_before_compute"]
            == (102400 if name == "partial" else 13221888),
            "available bytes",
        )
    need(
        s["arms"]["partial"]["output_sha256"] == s["arms"]["complete"]["output_sha256"],
        "same first rows",
    )
    arms = r["arms"]
    need(
        "".join(row["mode"] for row in arms) == "FLE" * 4 + "ELF" * 3
        and r["requested_bytes"] == len(arms) * 4 * 13221888
        and r["checked_full_slabs"] == len(arms) * 12
        and r["matched_prefix_f32"] == len(arms) * 256
        and r["swap_bytes"] == r["gpu_compute"] == r["model_forwards"] == 0
        and r["peak_cgroup_bytes"] < 224 * 2**20,
        "volume and resources",
    )
    for row in arms:
        ready, done = row["ready_ns"], row["done_ns"]
        need(
            len(ready) == len(done) == 4
            and row["first_ready_ns"] == min(ready)
            and row["all_ready_ns"] == max(ready)
            and all(0 < a <= b <= row["join_ns"] for a, b in zip(ready, done, strict=True)),
            "four-worker conservation",
        )
    for b, (offset, order) in enumerate(((3, "FLE"), (12, "ELF"))):
        group = arms[offset : offset + 9]
        for ctl in "FL":
            for k in ("all_ready_ns", "join_ns"):
                delta = [
                    group[j + order.index(ctl)][k] - group[j + order.index("E")][k]
                    for j in (0, 3, 6)
                ]
                need(
                    delta == [x[ctl][k] for x in r["pairs"][3 * b : 3 * b + 3]]
                    and median(delta) == r["median_ns"][b][ctl][k],
                    "independent paired prices",
                )
    need(Q["outcome"](arms)["decision"] == r["decision"], "outcome")
    if archive:
        part = archive / "part-01"
        family = part / "quartet-r01"

        def rows(file):
            return [json.loads(s) for s in file.read_bytes().splitlines()]

        need(
            sha(family / "receipt.json") == cmds["receipt_sha256"]
            and arms == rows(family / "arms.jsonl")
            and sha(family / "arms.jsonl") == cmds["arms_sha256"]
            and sha(family / "samples.jsonl") == cmds["samples_sha256"]
            and len(rows(family / "samples.jsonl")) == 9
            and sha(part / "tesy-stripe-quartet-c55-20261127-r01/receipt.json") == r["c55_sha256"],
            "sealed journals",
        )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--archive", type=Path)
    verify(cli.parse_args().archive)
    print("PASS_QUARTET_SERVICE_REVIEW")
