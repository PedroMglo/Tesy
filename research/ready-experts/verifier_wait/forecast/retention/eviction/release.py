"""Compare full-call and router-site I/O on the same mandatory GPT-OSS records."""

import argparse
import os
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
P = run_path(HERE.parent / "prefill_io.py")
F, S, E, M, IO, need, verified, sha, save = (
    P[k] for k in ("F", "S", "E", "M", "IO", "need", "verified", "sha", "save")
)
PROTO = "28ee3db28a9c14f7e27d7a52c376c08fb666a128565dcaf52849b5fbdd01103b"
REFERENCE = "a880e18bafc1067f5583ffffe70ddf6c6aded0c035a57506eca2d707eb2f963d"
SITES = 216
SIZE = S["ALIGNED"]


def native_source():
    template = HERE.parents[1] / "io/reader.cpp.in"
    need(sha(template) == P["PARENT_READER"], "reader identity")
    source = template.read_text()
    edits = {
        "std::vector<Window>, 46>": "std::vector<Window>, 216>",
        "call <= 46": "call <= 216",
        "c < 46;": "c < 216;",
        "c == 43": "c == 35",
        "(mode ? 2514u : 768u)": "34u",
        "(mode ? 2662u : 788u)": "726u",
    }
    for old, new in edits.items():
        need(source.count(old) == 1, "reader schema changed")
        source = source.replace(old, new)
    return source


def plan(a):
    reference = verified(a.reference / "receipt.json", REFERENCE)
    src = a.reference / "windows.tsv"
    need(sha(src) == reference["windows"], "earlier occurrence list")
    ref = verified(a.manifest / "receipt.json", M["PREP"]["MANIFEST"])
    idx = verified(a.manifest / "integral-index.json", ref["index_sha256"])
    need(
        ref["pack_sha256"] == reference["pack"]
        and ref["model_sha256"] == reference["model"]
        and ref["index_sha256"] == reference["index"],
        "shared physical source",
    )
    by_offset = {e["pack_offset"]: (e["layer"], e["expert"]) for e in idx["experts"]}
    need(len(by_offset) == 4608 and idx["weight_window"] == SIZE, "pack coverage")
    prior = verified(F["CONTROL"], F["CONTROL_SHA"])
    tx = verified(S["PATHS"]["transactions"], prior["inputs"]["transactions"])
    _, _, served, _ = E["inventory"](tx)
    by_call = [[], []]
    located = {}
    for c, t, layer, _, _, expert, _ in tx["reservations"]:
        if c > 2:
            break
        if expert not in served.get((c, t, layer), ()):
            k = c, layer, expert
            need(k not in located, "duplicate compulsory reservation")
            located[k] = (t - 1 + int(c == 2)) * 36 + layer
    steps = [[[] for _ in range(SITES)] for _ in range(2)]
    for line in src.read_text().splitlines():
        m, c, offset, *digests = line.split()
        if m != "1":
            continue
        c, offset = int(c), int(offset)
        layer, expert = by_offset[offset]
        site = located.pop((c, layer, expert))
        record = offset, *digests
        need(len(digests) == 3 and 0 <= site < SITES, "mandatory input")
        by_call[c - 1].append(record)
        steps[0][0 if c == 1 else 36].append(record)
        steps[1][site].append(record)
    need(not located and [len(v) for v in by_call] == [34, 692], "complete expert demands")
    windows = a.new_output_dir / "windows.tsv"
    with windows.open("x") as f:
        for mode, seq in enumerate(steps):
            for group, original in ((seq[:36], by_call[0]), (seq[36:], by_call[1])):
                need(Counter(v for site in group for v in site) == Counter(original), "same bytes")
            for i, site in enumerate(seq, 1):
                for row in sorted(site):
                    print(mode, i, *row, sep="\t", file=f)
    shared = {
        k: reference[k]
        for k in ("pack", "model", "index", "pack_path", "pack_stat", "model_path", "model_stat")
    }
    return dict(
        **shared,
        counts=[[len(s) for s in arm] for arm in steps],
        unique=len({r[0] for part in by_call for r in part}),
        windows=sha(windows),
        reference=REFERENCE,
    )


def parse(lines, plan):
    need(
        len(lines) == 3 + 4 * SITES
        and lines[0].split() == ["fd", *map(str, plan["pack_stat"])]
        and lines[-1] == "drained",
        "FD, extent or drain",
    )
    kind, n, ns = lines[1].split()
    need(kind == "parity" and int(n) == plan["unique"] and int(ns) > 0, "component parity")
    arms = []
    for i, mode in enumerate((0, 1, 1, 0)):
        groups = []
        for j, line in enumerate(lines[2 + i * SITES : 2 + (i + 1) * SITES]):
            kind, *fields = line.split()
            arm, m, group, count, batches, rd, wall = map(int, fields)
            need(
                kind == "step"
                and (arm, m, group, count) == (i + 1, mode, j + 1, plan["counts"][mode][j])
                and batches == (count + 3) // 4
                and wall >= rd >= 0
                and bool(rd) == bool(count),
                "group, release order, conservation or clocks",
            )
            groups.append([count, batches, rd, wall])
        calls = [
            [sum(row[k] for row in sub) for k in range(4)] for sub in (groups[:36], groups[36:])
        ]
        need([v[0] for v in calls] == [34, 692], "return boundaries")
        arms.append(
            dict(
                arm=i + 1,
                mode="R" if mode else "F",
                steps=calls,
                nonempty=sum(bool(v[0]) for v in groups),
                partial_batches=sum(bool(v[0] % 4) for v in groups),
                group_read_ns=[r[2] for r in groups],
            )
        )
    return dict(
        arms=arms,
        parity_records=int(n),
        parity_ns=int(ns),
        component_hashes=3 * int(n),
        timed_markers=9 * 726 * 4,
    )


def grade(obs):
    need(obs["status"] == "MEASURED" and obs["protocol"] == PROTO, "physical identity")
    arms = obs["timing"]["arms"]
    need(
        [a["mode"] for a in arms] == list("FRRF")
        and all([v[0] for v in a["steps"]] == [34, 692] for a in arms),
        "enrolled design",
    )
    cert = verified(HERE.parent / "evidence-entry-20261128-r01/receipt.json", P["ENTRY"])
    rows = []
    for a in arms:
        read = sum(v[2] for v in a["steps"])
        need(read == sum(a["group_read_ns"]), "read clocks")
        limits = []
        for price in cert["arms"]:
            first = [n + max(0, read - price["prefill_ns"]) for n in price["first_ns"]]
            device_slack = [
                10**10 - n + price["prefill_ns"] - read for n in reversed(price["first_ns"])
            ]
            limits.append(
                dict(
                    tag=price["tag"],
                    W=price["W"],
                    repeat=price["repeat"],
                    first_ns=first,
                    device_slack_ns=device_slack,
                    decode_ns=price["decode_ns"],
                    common_slack_ns=min(
                        10**10 - first[1], M["P"]["DECODE_MAX"] - price["decode_ns"]
                    ),
                )
            )
        rows.append(
            dict(
                arm=a["arm"],
                mode=a["mode"],
                call_read_ns=[v[2] for v in a["steps"]],
                read_ns=read,
                group_wall_ns=sum(v[3] for v in a["steps"]),
                batches=sum(v[1] for v in a["steps"]),
                partial=a["partial_batches"],
                nonempty=a["nonempty"],
                arms=limits,
            )
        )
    released = [p for row in rows if row["mode"] == "R" for p in row["arms"]]
    return dict(
        protocol=PROTO,
        evidence="MEASURED_DEVICE_TRACE_DERIVED_CLIENT",
        arms=rows,
        paired_R_minus_F_ns=[rows[i]["read_ns"] - rows[j]["read_ns"] for i, j in ((1, 0), (2, 3))],
        status=M["P"]["decision"](released),
        model_forwards=0,
    )


def physical(a, receipt):
    IO["run"](
        a,
        receipt,
        protocol=PROTO,
        source=HERE / "protocol.md",
        parse=parse,
        maximum_bytes=48_100_000_000,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="action", required=True)
    for name, keys in {
        "build": ("previous", "rpm"),
        "plan": ("manifest", "reference"),
        "grade": ("observed",),
    }.items():
        p = subs.add_parser(name)
        for k in keys:
            p.add_argument("--" + k, type=lambda s: Path(s).resolve(), required=True)
        dest = p.add_mutually_exclusive_group(required=True)
        dest.add_argument("--new-output-dir", type=lambda s: Path(s).resolve())
        if name == "grade":
            dest.add_argument("--check", type=Path)
    a = parser.parse_args()
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        need(sha(HERE / "protocol.md") == PROTO, "registered protocol")
        if a.action == "grade":
            result = grade(F["load"](a.observed)) | dict(observed_sha256=sha(a.observed))
            if a.check:
                need(F["load"](a.check) == result, "changed component or client grade")
            else:
                save(a.new_output_dir / "grade.json", result)
            print(result["status"], result["paired_R_minus_F_ns"])
            return
        commit, tree = M["B"]["version"]()
        result = M["build"](a, reader_source=native_source()) if a.action == "build" else plan(a)
        save(
            a.new_output_dir / "receipt.json",
            result
            | dict(
                commit=commit, tree=tree, protocol=PROTO, status="PASS", program=sha(Path(__file__))
            ),
        )
        print("PASS", sha(a.new_output_dir / "receipt.json"))
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise


if __name__ == "__main__":
    main()
