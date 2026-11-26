"""Verify paired timings, resident pages, copy requests and post-drain checks."""

import json
from pathlib import Path
from statistics import median

SLAB = 4_406_400
PAYLOAD = 3 * SLAB
OFFSETS = [1_838_905_376, 2_405_874_208, 1_273_411_616]
CUTS = dict(first_final=10_482_825_600, decode=7_941_645_345)
MODES = ("FILE", "ANON")


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def grade(order, data, stdout=""):
    first = {"FILE_FIRST": "FILE", "ANON_FIRST": "ANON"}[order]
    second = "ANON" if first == "FILE" else "FILE"
    seq = [first, second]
    for i in range(5):
        seq += [first, second] if i % 2 == 0 else [second, first]
    residues = [x % 4096 for x in OFFSETS]
    pages = [-(-(r + SLAB) // 4096) for r in residues]
    need(
        data["order"] == order
        and data["status"] == "PASS_HOT_TRANSFER_PROCESS"
        and data["offsets"] == OFFSETS
        and data["residues"] == residues
        and data["span_B"] == sum(pages) * 4096,
        "geometry",
    )
    need(
        not any(s.startswith(("REG ", "PEER ")) for s in stdout.splitlines()),
        "registration attempt or foreign peer operation",
    )
    rows = data["rows"]
    need(len(rows) == 12, "missing or extra fill")
    for i, (r, expected) in enumerate(zip(rows, seq, strict=True)):
        need(r["mode"] == expected and r["exact"] is (i < 2), "arm sequence")
        need(r["pages_before"] == r["pages_after"] == pages, "missing hot source pages")
        need(
            r["copies"] == 3
            and r["payload_B"] == PAYLOAD
            and r["poison_B"] == 576
            and r["roundtrip_B"] == (PAYLOAD if i < 2 else 576),
            "copy/roundtrip census",
        )
        need(
            r["input_blocks"] == r["major_faults"] == 0 and r["minor_faults"] >= 0,
            "source read during hot interval",
        )
        need(
            r["wall_ns"] == r["submit_ns"] + r["drain_ns"]
            and 0 < r["submit_ns"] <= r["wall_ns"]
            and min(r["process_ns"], r["thread_ns"], r["drain_ns"]) >= 0,
            "clock conservation",
        )
    times = rows[2:]
    pairs = []
    for i in range(0, 10, 2):
        xy = {r["mode"]: r["wall_ns"] for r in times[i : i + 2]}
        pairs.append(xy["FILE"] - xy["ANON"])
    stats = {}
    for mode in MODES:
        p = [r for r in times if r["mode"] == mode]
        wall = sum(r["wall_ns"] for r in p)
        med = int(median(r["wall_ns"] for r in p))
        stats[mode] = dict(
            median_ns=med,
            total_wall_ns=wall,
            total_B=5 * PAYLOAD,
            aggregate_B_s=5 * PAYLOAD * 10**9 // wall,
            median_B_s=PAYLOAD * 10**9 // med,
            median_submit_ns=int(median(r["submit_ns"] for r in p)),
            median_drain_ns=int(median(r["drain_ns"] for r in p)),
            median_thread_ns=int(median(r["thread_ns"] for r in p)),
            median_process_ns=int(median(r["process_ns"] for r in p)),
            cuts_at_median={k: PAYLOAD * 10**9 >= v * med for k, v in CUTS.items()},
        )
    return dict(
        status="REPRODUCED_HOT_TRANSFER_PROCESS",
        measurements=stats,
        paired_FILE_minus_ANON_ns=pairs,
        median_paired_ns=int(median(pairs)),
        fills=len(rows),
        payload_B=len(rows) * PAYLOAD,
        exact_roundtrip_B=2 * PAYLOAD,
    )


def reopen(arm):
    return grade(
        arm.name,
        json.loads((arm / "native/samples.json").read_bytes()),
        (arm / "stdout").read_text(),
    )


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("arm", type=Path)
    print(json.dumps(reopen(p.parse_args().arm), sort_keys=True))
