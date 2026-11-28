"""Diagnose the measured consumer arrival relative to its last required publication."""

import argparse
import gzip
import json
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent
D = run_path(HERE / "dispatch.py")


def diagnose(samples):
    D["grade"](samples)
    result = {}
    for tag, trials in samples.items():
        price = [r for r in trials["price"]["rows"] if r["block"]]
        population = {role: [r for r in price if r["role"] == role] for role in D["ARMS"]}
        population["best_single"] = [
            min(
                (
                    r
                    for r in price
                    if r["role"].startswith("ONE_") and (r["block"], r["direction"]) == (b, s)
                ),
                key=lambda r: r["consumer_ns"],
            )
            for b in range(1, 8)
            for s in range(2)
        ]
        result[tag] = {}
        for role, rows in population.items():
            last = [max(e[3] for e in r["events"]) for r in rows]
            arrival = [r["arrival_ns"] for r in rows]
            D["need"](len(last) == len(arrival) == 14, "incomplete paired population")
            result[tag][role] = dict(
                published_before_arrival=sum(p <= a for p, a in zip(last, arrival, strict=True)),
                trials=len(rows),
                median_last_publish_ns=median(last),
                median_arrival_ns=median(arrival),
                median_arrival_minus_last_ns=median(
                    a - p for a, p in zip(arrival, last, strict=True)
                ),
            )
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory", type=Path)
    args = p.parse_args()
    samples = json.loads(gzip.decompress((args.directory / "samples.json.gz").read_bytes()))
    result = diagnose(samples)
    D["need"](
        result == json.loads((args.directory / "arrivals.json").read_bytes()),
        "archived arrival diagnostic",
    )
    print({k: v["ALL"]["published_before_arrival"] for k, v in result.items()})
