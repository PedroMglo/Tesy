"""Measure the mandatory prefill I/O on the same four-buffer ring as the decode experiment."""

import argparse
import os
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
E = run_path(HERE / "entry.py")
R, F, T, S, need, verified, sha, save = (
    E[k] for k in ("R", "F", "T", "S", "need", "verified", "sha", "save")
)
IO = run_path(HERE.parent / "io/run.py")
M = IO["M"]
PROTO = "c6ce6cb8c404f8d5db80ce55c5650c36d1ac4f86eb014805c3b140746674e256"
ENTRY = "7431439e4ae08b5c4a802687489c73e39d263da7ff5019de81cc0446dda249c1"
PARENT_READER = "60dfc610d4ac84ffb0de0b8fb25ec1b94b1588ea56d4531c344e6cbf625f8326"
COUNTS = [[34, 858], [34, 692]]
MAX_BYTES = 4128 * S["ALIGNED"]


def native_source():
    path = HERE.parent / "io/reader.cpp.in"
    need(sha(path) == PARENT_READER, "frozen physical reader")
    source = path.read_text()
    # Only the input contract changes. The ring, allocation, parity, per-batch
    # clocks, per-occurrence markers, ordering of paired arms and drain are shared.
    edits = (
        ("std::vector<Window>, 46>", "std::vector<Window>, 2>"),
        ("call <= 46", "call <= 2"),
        (
            "step.back().offset < w.offset",
            "(step.back().offset < w.offset || (mode == 0 && step.back().offset == w.offset))",
        ),
        ("c < 46;", "c < 2;"),
        (
            'if (c == 43) check(count == (mode ? 2514u : 768u), "first cut");',
            'if (c == 0) check(count == 34u, "first call");',
        ),
        ("2662u : 788u", "726u : 892u"),
    )
    for before, after in edits:
        need(source.count(before) == 1, "changed parser boundary")
        source = source.replace(before, after)
    return source


def plan(a):
    cert = verified(HERE / "evidence-entry-20261128-r01/receipt.json", ENTRY)
    previous = verified(HERE / "evidence-20261128-r01/receipt.json", cert["prior"])
    tx = verified(S["PATHS"]["transactions"], previous["sources"]["transactions"])
    base, _, mirror, lineage = E["inventory"](tx)
    need(all(cert[k] == v for k, v in lineage.items()), "ownership certificate")
    ref = verified(a.manifest / "receipt.json", M["PREP"]["MANIFEST"])
    index = verified(a.manifest / "integral-index.json", ref["index_sha256"])
    experts = {(e["layer"], e["expert"]): e for e in index["experts"]}
    need(len(experts) == 4608 and index["weight_window"] == S["ALIGNED"], "full C291 index")
    inputs = [[[], []], [[], []]]
    for call, tile, layer, _, _, expert, _ in tx["reservations"]:
        if call > 2:
            continue
        site = call, tile, layer
        for seq, table in zip(inputs, (base, mirror), strict=True):
            if expert not in table.get(site, ()):
                seq[call - 1].append(experts[layer, expert])
    counts = [[len(step) for step in seq] for seq in inputs]
    need(counts == COUNTS, "per-return reads")
    unique = set()
    windows = a.new_output_dir / "windows.tsv"
    with windows.open("x") as f:
        for mode, seq in enumerate(inputs):
            for call, step in enumerate(seq, 1):
                offsets = [e["pack_offset"] for e in step]
                need(not mode or len(set(offsets)) == len(step), "duplicate compulsory read")
                for e in sorted(step, key=lambda row: row["pack_offset"]):
                    off = e["pack_offset"]
                    parts = e["components"][:3]
                    need(
                        off % 4096 == 0
                        and [v["packed_relative_offset"] for v in parts] == [0, 4406400, 8812800]
                        and all(v["type"] == "mxfp4" and v["size_bytes"] == 4406400 for v in parts),
                        "weight layout",
                    )
                    unique.add(off)
                    print(mode, call, off, *(v["sha256"] for v in parts), sep="\t", file=f)
    return dict(
        counts=counts,
        unique=len(unique),
        windows=sha(windows),
        certificate=ENTRY,
        manifest=M["PREP"]["MANIFEST"],
        index=ref["index_sha256"],
        pack_path=ref["pack_path"],
        pack_stat=[ref["pack_stat"][k] for k in M["STAT"]],
        pack=ref["pack_sha256"],
        model_path=ref["model_path"],
        model_stat=[ref["model_stat"][k] for k in M["STAT"]],
        model=ref["model_sha256"],
    )


def parse(lines, plan):
    need(
        len(lines) == 11
        and lines[0].split() == ["fd", *map(str, plan["pack_stat"])]
        and lines[-1] == "drained",
        "FD, result extent or drain",
    )
    name, count, ns = lines[1].split()
    need(
        name == "parity"
        and int(count) == plan["unique"]
        and int(ns) > 0
        and plan["counts"] == COUNTS,
        "SHA-256 parity or plan",
    )
    arms = []
    for i, mode in enumerate((0, 1, 1, 0)):
        steps = []
        for j in range(2):
            head, *fields = lines[2 + i * 2 + j].split()
            arm, m, c, n, b, rd, wall = map(int, fields)
            need(
                head == "step"
                and (arm, m, c, n) == (i + 1, mode, j + 1, COUNTS[mode][j])
                and b == (n + 3) // 4
                and wall >= rd > 0,
                "call population or clock",
            )
            steps.append([n, b, rd, wall])
        arms.append(dict(arm=i + 1, mode="E" if mode else "D", steps=steps))
    return dict(
        arms=arms,
        parity_records=int(count),
        parity_ns=int(ns),
        component_hashes=3 * int(count),
        timed_markers=9 * 2 * sum(map(sum, COUNTS)),
    )


def physical(a, receipt):
    IO["run"](
        a,
        receipt,
        protocol=PROTO,
        source=HERE / "io-protocol.md",
        parse=parse,
        maximum_bytes=MAX_BYTES,
    )


def grade(raw):
    need(raw["status"] == "MEASURED" and raw["protocol"] == PROTO, "physical lineage")
    cert = verified(HERE / "evidence-entry-20261128-r01/receipt.json", ENTRY)
    before = verified(HERE / "evidence-20261128-r01/receipt.json", cert["prior"])
    rows = []
    for v in raw["timing"]["arms"]:
        tag = v["mode"]
        ns = sum(s[2] for s in v["steps"])
        limits = []
        source = cert["arms"] if tag == "E" else before["arms"]["off"]
        for a in source:
            lowest = a["prefill_ns"] + 10**10 - a["first_ns"][1]
            highest = a["prefill_ns"] + 10**10 - a["first_ns"][0]
            extra = max(0, ns - a["prefill_ns"])
            limits.append(
                dict(
                    tag=a["tag"],
                    W=a["W"],
                    repeat=a["repeat"],
                    prefill_ns=a["prefill_ns"],
                    free_compute_slack_ns=[lowest - ns, highest - ns],
                    first_ns=[n + extra for n in a["first_ns"]],
                    decode_ns=a["decode_ns"],
                    common_slack_ns=min(
                        10**10 - a["first_ns"][1] - extra, M["P"]["DECODE_MAX"] - a["decode_ns"]
                    ),
                )
            )
        rows.append(
            dict(
                arm=v["arm"],
                mode=tag,
                read_ns=ns,
                call_read_ns=[s[2] for s in v["steps"]],
                step_wall_ns=sum(s[3] for s in v["steps"]),
                requested_B=sum(s[0] for s in v["steps"]) * S["ALIGNED"],
                arms=limits,
            )
        )
    limits = [a for v in rows if v["mode"] == "E" for a in v["arms"]]
    need(len(limits) == 16 and [v["mode"] for v in rows] == list("DEED"), "paired coverage")
    slack = [v["free_compute_slack_ns"] for v in limits]
    device = (
        "GO_CONSUMER_FIXTURE_ONLY"
        if min(s[0] for s in slack) >= 0
        else "NO_GO"
        if max(s[1] for s in slack) < 0
        else "INCONCLUSIVE"
    )
    status = M["P"]["decision"](limits)
    return dict(
        device=device,
        client=status,
        evidence="MEASURED_READS_TRACE_DERIVED_CLIENT",
        arms=rows,
        parity_records=raw["timing"]["parity_records"],
        parity_ns=raw["timing"]["parity_ns"],
        requested_B=raw["requested_B"],
        protocol=PROTO,
        program=sha(Path(__file__)),
        forwards=0,
    )


def cli():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    for name, keys in (
        ("build", ("previous", "rpm")),
        ("plan", ("manifest",)),
        ("grade", ("observed",)),
    ):
        opt = sub.add_parser(name)
        for k in keys:
            opt.add_argument("--" + k, required=True, type=lambda s: Path(s).resolve())
        out = opt.add_mutually_exclusive_group(required=True)
        out.add_argument("--new-output-dir", type=Path)
        if name == "grade":
            out.add_argument("--check", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    dest = a.new_output_dir
    if dest:
        dest = dest.resolve()
        a.new_output_dir = dest
        dest.mkdir()
    try:
        need(sha(HERE / "io-protocol.md") == PROTO, "prefill I/O protocol")
        if a.action == "grade":
            result = grade(F["load"](a.observed)) | dict(observed_sha256=sha(a.observed))
            if dest:
                save(dest / "grade.json", result)
            else:
                need(result == F["load"](a.check), "client or device grade changed")
            print(result["device"], result["client"])
        else:
            commit, tree = M["B"]["version"]()
            data = M["build"](a, reader_source=native_source()) if a.action == "build" else plan(a)
            save(
                dest / "receipt.json",
                data
                | dict(
                    status="PASS",
                    commit=commit,
                    tree=tree,
                    protocol=PROTO,
                    program=sha(Path(__file__)),
                ),
            )
            print("PASS", sha(dest / "receipt.json"))
    except Exception as exc:
        if dest:
            save(dest / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise


if __name__ == "__main__":
    cli()
