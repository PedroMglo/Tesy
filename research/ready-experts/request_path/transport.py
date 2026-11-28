"""Prepare identical demand and runahead reads and use the established physical supervisor."""

import argparse
import os
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
IO = HERE.parent / "verifier_wait/forecast/io"
LEGACY = run_path(IO / "run.py")
M = LEGACY["M"]
need, sha, verified, save = (LEGACY[k] for k in ("need", "sha", "verified", "save"))
METHOD = "2b7c11ef01554d85c52fa2e0ae8b8d9d4d176d738271d9a467d4701ec902969d"
PROOF = HERE / "evidence-20261128-r03"
SPANS = "1a0a8850446b0c81c018f39f79c258843047958284510115c0086b1fc95e854b"
SIZE = 13_221_888


def workload():
    s = run_path(HERE / "source.py")
    replay = run_path(HERE / "replay.py")
    native, _, hits = s["inputs"]()
    need(sha(PROOF / "spans.json.gz") == SPANS, "whole-request evidence")
    spans = s["F"]["unpack"](PROOF / "spans.json.gz")
    population = None
    for tag, obs in spans.items():
        jobs = native[tag]["jobs"]
        chosen = []
        for i, (site, _, _, _, _, demanded, _) in enumerate(obs["waves"]):
            part = replay["PHASES"].index(replay["phase"](site[0]))
            for j in demanded:
                if jobs[j][1] == site and j not in hits:
                    layer, _, _, expert = jobs[j][0]
                    chosen.append((part, i, j, layer, expert))
        need(len(chosen) == len({j for _, _, j, _, _ in chosen}) == 1519, "compulsory misses")
        need(population is None or chosen == population, "routes or reservation order differ")
        population = chosen
    return spans, population


def plan(a, chosen=None):
    if chosen is None:
        _, chosen = workload()
    manifest = verified(a.manifest / "receipt.json", M["PREP"]["MANIFEST"])
    index = verified(a.manifest / "integral-index.json", manifest["index_sha256"])
    experts = {(e["layer"], e["expert"]): e for e in index["experts"]}
    need(len(experts) == 4608 and index["weight_window"] == SIZE, "expert index")
    counts, phases, offsets = Counter(), Counter(), set()
    windows = a.new_output_dir / "windows.tsv"
    with windows.open("x") as f:
        for part, i, _, layer, expert in chosen:
            item = experts[layer, expert]
            parts = item["components"][:3]
            off = item["pack_offset"]
            need(
                off % 4096 == 0
                and [p["packed_relative_offset"] for p in parts] == [0, 4406400, 8812800]
                and all(p["type"] == "mxfp4" and p["size_bytes"] == 4406400 for p in parts),
                "weight geometry",
            )
            print(part, i, off, *(p["sha256"] for p in parts), sep="\t", file=f)
            counts[i] += 1
            phases[part] += 1
            offsets.add(off)
    stats = {k: [manifest[k][field] for field in M["STAT"]] for k in ("pack_stat", "model_stat")}
    return dict(
        windows=sha(windows),
        counts=sorted(counts.items()),
        phases=sorted(phases.items()),
        unique=len(offsets),
        model=manifest["model_sha256"],
        pack=manifest["pack_sha256"],
        index=manifest["index_sha256"],
        pack_path=manifest["pack_path"],
        model_path=manifest["model_path"],
        **stats,
    )


def build(a):
    original = (IO / "reader.cpp.in").read_text()
    anchor = "static auto work_file("
    need(original.count(anchor) == 1, "marker helper")
    text = original.split(anchor)[0] + (HERE / "transport.cpp.in").read_text()
    return M["build"](a, reader_source=text)


def parse(lines, spec):
    need(
        lines[0].split() == ["fd", *map(str, spec["pack_stat"])] and lines[-1] == "drained",
        "physical FD or shutdown",
    )
    kind, count, elapsed = lines[1].split()
    unique = int(count)
    need(
        kind == "parity" and unique == spec["unique"] and int(elapsed) > 0, "full component checks"
    )
    rows, cursor = [], 2
    for arm in range(1, 5):
        early = arm in (2, 3)
        expected = spec["phases"] if early else spec["counts"]
        cohort = []
        for group, n in expected:
            kind, *fields = lines[cursor].split()
            a, g, size, rd, wall = map(int, fields)
            need(
                kind == "group" and (a, g, size) == (arm, group, n) and wall >= rd > 0 and n > 0,
                "arm, group, population or clock",
            )
            cohort.append([group, size, rd, wall])
            cursor += 1
        need(sum(row[1] for row in cohort) == 1519, "incomplete arm")
        rows.append(cohort)
    need(cursor == len(lines) - 1, "unaccounted output")
    return dict(
        parity_records=unique,
        parity_ns=int(elapsed),
        component_hashes=3 * unique,
        timed_markers=9 * 4 * 1519,
        arms=rows,
    )


def physical(a, receipt, *, method=METHOD, protocol_file=HERE / "transport-protocol.md"):
    window = verified(a.c55 / "receipt.json", a.c55_sha256)
    need(window["model_device"].split("[")[0] == "/dev/nvme0n1p3", "target NVMe ancestry")
    device = Path("/sys/class/nvme/nvme0")

    def link():
        return {
            k: (device / "device" / k).read_text().strip()
            for k in (
                "current_link_speed",
                "current_link_width",
                "max_link_speed",
                "max_link_width",
            )
        }

    before = link()
    need(
        before["current_link_speed"] == "16.0 GT/s PCIe" and before["current_link_width"] == "4",
        "unregistered PCIe geometry",
    )
    receipt.update(
        pcie=before,
        nvme_model=(device / "model").read_text().strip(),
        nvme_firmware=(device / "firmware_rev").read_text().strip(),
    )
    LEGACY["run"](
        a,
        receipt,
        protocol=method,
        source=protocol_file,
        parse=parse,
        maximum_bytes=120 << 30,
        requested_records=lambda t, _p: 4 * 1519 + t["parity_records"],
    )
    receipt["status"] = "FAIL_PRESERVED"
    need(link() == before, "changed NVMe link")
    receipt["status"] = "MEASURED"


def main():
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "physical":
        del sys.argv[1]
        LEGACY["main"](physical)
        return
    cli = argparse.ArgumentParser(description=__doc__)
    actions = cli.add_subparsers(dest="action", required=True)
    for name, fields in (("plan", ("manifest",)), ("build", ("previous", "rpm"))):
        sub = actions.add_parser(name)
        for field in (*fields, "new-output-dir"):
            sub.add_argument("--" + field, required=True, type=lambda p: Path(p).resolve())
    a = cli.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        commit, tree = M["B"]["version"]()
        need(sha(HERE / "transport-protocol.md") == METHOD, "protocol hash")
        result = (plan if a.action == "plan" else build)(a)
        save(
            a.new_output_dir / "receipt.json",
            result
            | dict(
                status="PASS", commit=commit, tree=tree, protocol=METHOD, driver=sha(Path(__file__))
            ),
        )
    except Exception as exc:
        save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise


if __name__ == "__main__":
    main()
