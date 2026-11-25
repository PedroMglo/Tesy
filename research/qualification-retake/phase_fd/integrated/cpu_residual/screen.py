"""Reproduce the static C281 thread contract and two historical single-thread dot contrasts."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
Q = HERE.parents[2]
PINS = {
    "receipt.json": "cb191e31c2e3ee547a01228065a3c4253bdb312dd1e561d361f75365f065356a",
    "argv.json": "1a8425b306951a2029ddf3a0656e7565b17bb7f884dccdcc0fe61af214443646",
    "resource-protocol.json": "fb5cfb14db7f4dd72c5d3688ba850e5b2650b0f02925fcb2a490d13915b8c358",
    "arms.tsv": "880024dfede16b7f93529983b8c12345a44428fb503b9fec6dc203c74256430d",
}


def frozen(path):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != PINS[path.name]:
        raise ValueError("input identity: " + path.name)
    return data


def evidence(c281):
    frozen(c281 / "receipt.json")
    argv = json.loads(frozen(c281 / "argv.json"))["command"]
    argv = argv[max(i for i, value in enumerate(argv) if value == "--") + 1 :]
    options = {
        name: int(argv[argv.index(name) + 1])
        for name in ("-t", "-tb", "-np", "--moe-stream-io-threads")
    }
    runtime = json.loads(frozen(c281 / "resource-protocol.json"))["parallel_runtime"]["environment"]
    rows = csv.DictReader(
        frozen(Q / "mxfp4_vnni/evidence/arms.tsv").decode().splitlines(), delimiter=" "
    )
    samples = {}
    for row in rows:
        if row["variant"] == "R":
            samples.setdefault((row["regime"], int(row["cpu"])), []).append(int(row["duration_ns"]))
    scenarios = {}
    for regime in ("hot", "stream"):
        med = {n: median(samples[(regime, n)]) for n in (0, 4)}
        ratio = med[4] / med[0]
        scenarios[regime] = {
            "median_native_ns": med,
            "raw_native_ns": {n: samples[(regime, n)] for n in (0, 4)},
            "zen5_to_zen5c_rate": ratio,
            "ideal_four_plus_four_vs_eight_compact_gain_fraction": 1 - 8 / (4 * ratio + 4),
        }
    return {
        "class": "REPRODUCED_STATIC_AND_ESTIMATED_PLACEMENT",
        "c281": options,
        "parallel_runtime": runtime,
        "single_thread_scenarios": scenarios,
        "tid_cpu_placement": "UNKNOWN",
        "new_forwards": 0,
        "source_sha256": PINS,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--closed-c281", type=Path, required=True)
    p.add_argument("--new-output", type=Path, required=True)
    a = p.parse_args()
    result = evidence(a.closed_c281)
    with a.new_output.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
