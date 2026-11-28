"""Measure three peer reads with four fixed lanes and authenticated pack extents."""

import argparse
import os
import re
import subprocess
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent
IO = run_path(HERE.parents[3] / "io/run.py")
M, sha, need, verified, save = (IO[k] for k in ("M", "sha", "need", "verified", "save"))
METHOD = "44163ffcd63410e5e8baaf0d1921e2cc8f960f1013abc00abd44e12971564a96"
FRONTIER = "c718059d4b27f09282457bf59a29d0784f0f62f6e7c67fcf433c16c7530e7296"
SIZE = 13221888
SLAB = 4406400
METRICS = ["three_peers", "all_reads", "copies_and_drain"]


def plan(a):
    frontier = verified(a.frontier, FRONTIER)
    need(frontier["method"] == METHOD, "frontier protocol")
    ref = verified(a.manifest / "receipt.json", M["PREP"]["MANIFEST"])
    idx = verified(a.manifest / "integral-index.json", ref["index_sha256"])
    by_id = {128 * e["layer"] + e["expert"]: e for e in idx["experts"]}
    need(len(by_id) == 4608 and idx["weight_window"] == SIZE, "target index")
    groups = frontier["groups"]
    labels = ["physical_54"] + (["causal_353"] if frontier["common_quartets"] else [])
    need(set(labels) == set(groups), "quartet identity")
    stat = [ref["pack_stat"][k] for k in M["STAT"]]
    windows = a.new_output_dir / "windows.tsv"
    with windows.open("x") as f:
        print(*stat, len(labels), sep="\t", file=f)
        for label in labels:
            keys = groups[label]
            need(len(keys) == len(set(keys)) == 4 and len({k // 128 for k in keys}) == 1, "quartet")
            for key in keys:
                record = by_id[key]
                off, matrices = record["pack_offset"], record["components"][:3]
                need(
                    off >= 0
                    and off % 4096 == 0
                    and off + SIZE <= stat[2]
                    and [v["packed_relative_offset"] for v in matrices] == [0, SLAB, 2 * SLAB]
                    and all(v["type"] == "mxfp4" and v["size_bytes"] == SLAB for v in matrices),
                    "matrix geometry",
                )
                print(off, *(m["sha256"] for m in matrices), sep="\t", file=f)
    return dict(
        labels=labels,
        groups=groups,
        frontier=FRONTIER,
        manifest=M["PREP"]["MANIFEST"],
        model=ref["model_sha256"],
        pack=ref["pack_sha256"],
        index=ref["index_sha256"],
        model_path=ref["model_path"],
        pack_path=ref["pack_path"],
        model_stat=[ref["model_stat"][k] for k in M["STAT"]],
        pack_stat=stat,
        windows=sha(windows),
        expected_records=229 * len(labels),
    )


def build(a, *, reader_source=None):
    old = verified(a.previous / "receipt.json", M["HISTORIC_BUILD"])
    cxx = "/usr/bin/g++"
    need(sha(cxx) == old["compiler_sha256"], "pinned compiler")
    src = HERE / "peer.cpp" if reader_source is None else reader_source
    exe = a.new_output_dir / "reader"
    cmd = [
        cxx,
        "-std=c++20",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-pthread",
        str(src),
        "-lcrypto",
        "-o",
        str(exe),
    ]
    with (a.new_output_dir / "compiler.log").open("x") as log:
        subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=45)
    ldd = subprocess.check_output(["ldd", exe], text=True, timeout=5)
    with (a.new_output_dir / "ldd.txt").open("x") as f:
        f.write(ldd)
    libraries = {p: sha(p) for p in re.findall(r"(/\S+) \(0x", ldd)}
    need(
        {"libc.so.6", "libcrypto.so.3", "libstdc++.so.6"} <= {Path(p).name for p in libraries}
        and "not found" not in ldd
        and all(old["libraries"].get(p) == h for p, h in libraries.items()),
        "runtime library closure",
    )
    return dict(
        command=cmd,
        compiler=sha(cxx),
        source=sha(src),
        binary=sha(exe),
        parent=M["HISTORIC_BUILD"],
        libraries=libraries,
    )


def schedule():
    for stage in range(2):
        for order, p in [(-1, 0), *((o, p) for o in (0, 1) for p in range(1, 8))]:
            for leg in range(2):
                alternate = int((order == 1) != bool(leg))
                yield (stage, order, p, stage * alternate, (1 - stage) * alternate)


def grade(rows):
    paired = defaultdict(dict)
    for stage, order, p, hit, trace, *clocks in rows:
        if order >= 0:
            paired[stage, order, p][hit if stage else trace] = clocks
    ratios, prices = [], []
    for order in range(2):
        neutral = [paired[0, order, p] for p in range(1, 8)]
        ratio = median(Fraction(pair[1][0], pair[0][0]) for pair in neutral)
        ratios.append([ratio.numerator, ratio.denominator])
        medians, effects = {}, {}
        for pos, name in enumerate(METRICS):
            differences = [
                paired[1, order, p][1][pos] - paired[1, order, p][0][pos] for p in range(1, 8)
            ]
            effects[name] = differences
            medians[name] = median(differences)
        prices.append(dict(order=["DH", "HD"][order], H_minus_D_ns=effects, median_ns=medians))
    primary = [o["median_ns"]["three_peers"] for o in prices]
    decision = (
        "GO_LOCAL" if max(primary) < 0 else "NO_GO_LOCAL" if min(primary) > 0 else "INCONCLUSIVE"
    )
    neutral = all(Fraction(97, 100) <= Fraction(*r) <= Fraction(103, 100) for r in ratios)
    return dict(
        neutrality="PASS" if neutral else "NOT_NEUTRAL",
        median_ON_over_OFF=ratios,
        paired=prices,
        decision=decision,
    )


def parse(lines, plan):
    labels = plan["labels"]
    n = len(labels)
    need(
        n in (1, 2)
        and len(lines) == 2 + n * 60
        and lines[0].split() == ["fd", *map(str, plan["pack_stat"])],
        "fd identity or row count",
    )
    groups = {}
    for g, label in enumerate(labels):
        numeric = []
        for i, expected in enumerate(schedule()):
            name, *tail = lines[1 + 60 * g + i].split()
            fields = list(map(int, tail))
            need(
                name == "row" and len(fields) == 17 and fields[:6] == [g, *expected],
                "protocol order or cohort",
            )
            peers, all_reads, drain = fields[6:9]
            need(0 < peers <= all_reads <= drain, "barriers out of order")
            for w in range(4):
                start, end = fields[9 + 2 * w : 11 + 2 * w]
                need(
                    0 <= start < end <= (peers if w < 3 else all_reads)
                    if expected[-1]
                    else start == end == 0,
                    "individual clock or OFF contamination",
                )
            numeric.append(fields[1:9])
        groups[label] = grade(numeric)
    name, *tail = lines[-1].split()
    footer = list(map(int, tail))
    need(
        name == "drained" and footer == [61 * n, 61 * n, 61 * n, 46 * n, *([183 * n] * 4)],
        "read or SHA conservation",
    )
    requested = sum(footer[:4])
    need(requested == plan["expected_records"] == 229 * n, "enrolled bytes")
    return dict(
        groups=groups,
        trials=60 * n,
        requested_records=requested,
        destination_hashes=720 * n,
        parity_hashes=12 * n,
        records_by_lane=footer[:4],
        forwards=0,
        http_requests=0,
    )


def physical(a, receipt):
    IO["run"](
        a,
        receipt,
        protocol=METHOD,
        source=HERE / "protocol.md",
        parse=parse,
        maximum_bytes=10_000_000_000,
        requested_records=lambda t, _: t["requested_records"],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    for action, keys in (("build", ("previous",)), ("plan", ("manifest", "frontier"))):
        p = subs.add_parser(action)
        for k in (*keys, "new-output-dir"):
            p.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
    p = subs.add_parser("check")
    p.add_argument("evidence", type=Path)
    args = parser.parse_args()
    need(sha(HERE / "protocol.md") == METHOD, "registered protocol")
    if args.action == "check":
        meta = IO["load"](args.evidence / "device.json")
        proof = parse((args.evidence / "service.txt").read_text().splitlines(), meta["plan"])
        need(
            meta["timing"] == proof
            and sha(args.evidence / "service.txt") == meta["stdout_sha256"]
            and sha(args.evidence / "frontier.json") == FRONTIER,
            "published device receipt",
        )
        print({k: v["decision"] for k, v in proof["groups"].items()})
        return
    os.umask(0o077)
    args.new_output_dir.mkdir()
    try:
        commit, tree = M["B"]["version"]()
        result = (plan if args.action == "plan" else build)(args)
        save(
            args.new_output_dir / "receipt.json",
            result
            | dict(commit=commit, tree=tree, protocol=METHOD, status="PASS", program=sha(__file__)),
        )
        print("PASS", sha(args.new_output_dir / "receipt.json"))
    except Exception as exc:
        save(args.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise


if __name__ == "__main__":
    main()
