"""Identify the first overlap that exceeds 1,252 and the transport cut that still fits."""

import argparse
import gzip
import json
from collections import defaultdict
from itertools import groupby
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
V = run_path(HERE / "visit.py")
need, verified = V["need"], V["verified"]


def run():
    shadow = verified(
        HERE / "evidence-shadow-20261128-r01/decision.json",
        "f38930fab6f567aa1f3f1d81af362d490676b18541aa757a470734ed7b9a302b",
    )
    delivery = verified(
        HERE / "evidence-visit-20261128-r01/decision.json",
        "fa51eb8fa52503dbe86437d6135812a470c0d0fa0b72ffb3ba8e2cdc478a573f",
    )
    receipt = HERE / "evidence-switch-20261128-r01/witness.json.gz"
    need(V["sha"](receipt) == V["WITNESS"], "input")
    data = json.loads(gzip.decompress(receipt.read_bytes()))["natural_nominal"]
    events = defaultdict(list)
    for row in data["events"]:
        events[tuple(row[1:3])].append(row)
    entry = set(data["entry"])
    predicted = {tuple(r["site"][1:]): r for r in shadow["affected"]}
    failed = []
    for site, rows in groupby(data["waves"], key=lambda r: tuple(r[1:3])):
        begin = entry.copy()
        for _, _, _, k, _, lost in events.pop(site, []):
            entry.difference_update(lost)
            entry.add(k)
        if site not in predicted:
            continue
        own = []
        parking = []
        for _, _, _, ix, batch in rows:
            parking = batch + parking[: max(0, 4 - len(batch))] if ix >= 0 else batch
            need(len(parking) == len(set(parking)), "parking collision")
            own.append(set(parking))
        overlap = [a | b for a, b in zip(own, own[1:] + [set()], strict=True)]
        last = {k: i for i, keys in enumerate(overlap) for k in keys}
        live = begin & (set(last) | entry)
        peak = max(len(begin), len(entry))
        for i, keys in enumerate(overlap):
            new = keys - live
            before = len(live)
            live.update(keys)
            peak = max(peak, len(live))
            if len(live) > 1252:
                early = sorted(k for k in new - own[i])
                failed.append(
                    dict(
                        tile=site[0],
                        layer=site[1],
                        wave=i,
                        live_before=before,
                        new=len(new),
                        live_overlap=len(live),
                        required_now=len(own[i]),
                        first_preload_candidates=[k % 128 for k in early],
                        deficit=len(live) - 1252,
                    )
                )
            live.difference_update({k for k in keys - entry if last[k] == i})
        need(live == entry and peak == predicted[site]["two"]["peak"], "independent peak")
    need(not events, "ungraded visit")
    retained = [r for r in delivery["visits"] if predicted[tuple(r["site"])]["two"]["peak"] <= 1252]
    count = sum(r["held"] for r in retained)
    need(count == len(shadow["fit_jobs"]), "native subset")
    return dict(
        failed_overlaps=failed,
        eligible_visits=len(retained),
        eligible_jobs=count,
        cpu_prefill_reads_with_fallback=data["native"] - count,
        paired_service_saved_ns_summing_measured_cells=[
            sum(r["service_saved_ns"][i] for r in retained) for i in (0, 1)
        ],
        projected_client_saved_ns=shadow["saved_client_ns"],
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--check", type=Path)
    args = cli.parse_args()
    result = run()
    if args.check:
        need(result == json.loads(args.check.read_bytes()), "subset receipt")
    else:
        print(json.dumps(result, sort_keys=True, indent=2))
