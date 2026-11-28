"""Measure only the nine paid CPU visits that a layer-local ownership change could affect."""

import argparse
import gzip
import json
import os
import sys
from collections import defaultdict
from itertools import groupby
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
T = run_path(HERE.parent / "transport.py")
M, LEGACY, need, sha, verified, save = (
    T[k] for k in ("M", "LEGACY", "need", "sha", "verified", "save")
)
METHOD = "a597b82616ec4483c4a2c75448f9f83bfc558d858b88f8cee45b22733c2e9de9"
PROOF = HERE / "evidence-switch-20261128-r01"
WITNESS = "137702200da92aa1e2f2d4f7fac1c6bd95759813ef7c9ad8640d67eee3d40e64"
DECISION = "df9fb47be61c0c45a66239aa7d86c7edcf60ba306a1db1a762c55525b86cdb76"


def cases():
    need(sha(PROOF / "witness.json.gz") == WITNESS, "boundary observations")
    w = json.loads(gzip.decompress((PROOF / "witness.json.gz").read_bytes()))["natural_nominal"]
    r = verified(PROOF / "decision.json", DECISION)["cases"]["natural_nominal"]
    targets = dict(r["dispensable_jobs"])
    spares = {tuple(row["site"]): row["surplus"] for row in r["visits"]}
    by_site = defaultdict(list)
    for event in w["events"]:
        by_site[tuple(event[1:3])].append(event)
    members = set(w["entry"])
    visits, capacity = [], []
    for site, group in groupby(w["waves"], key=lambda row: tuple(row[1:3])):
        batches = [set(row[-1]) for row in group]
        at_start = members.copy()
        paid = []
        for ix, _, _, key, miss, dropped in by_site.pop(site, []):
            need(bool(miss) == (key not in members), "missing or duplicate read")
            if miss:
                paid.append((ix, key, int(ix in targets)))
            members.difference_update(dropped)
            members.add(key)
        used = set().union(*batches)
        need(len(used) == sum(map(len, batches)), "expert assigned to two native waves")
        initial_live = at_start & (members | used)
        peak_active = peak_park = max(len(at_start), len(members))
        live = set(initial_live)
        parking = set()
        for wanted in batches:
            active = live | wanted
            peak_active = max(peak_active, len(active))
            # With fewer than four own IDs the manager borrows from its previous pool.
            # Keeping every candidate for this borrow covers unknown physical ID order.
            if len(wanted) < 4:
                parking |= wanted
            else:
                parking = wanted
            peak_park = max(peak_park, len(active | parking))
            live = active - (wanted - members)
        need(live == members, "incomplete restored visit")
        capacity.append([*site, len(initial_live), peak_active, peak_park])
        if spares[site]:
            need(
                all(targets[i] in at_start for i in spares[site]),
                "hold requires unobserved prefetch",
            )
            visits.append((site, paid))
    need(
        members == set(w["end"]) and not by_site and len(visits) == 9 and len(capacity) == 125,
        "coverage",
    )
    return visits, capacity


def plan(a):
    visits, cap = cases()
    src = run_path(HERE.parent / "source.py")
    native, _, _ = src["inputs"]()
    spans = src["F"]["unpack"](HERE.parent / "evidence-20261128-r03/spans.json.gz")
    indices = {tuple(w[0]): i for i, w in enumerate(spans["P97"]["waves"])}
    manifest = verified(a.manifest / "receipt.json", M["PREP"]["MANIFEST"])
    index = verified(a.manifest / "integral-index.json", manifest["index_sha256"])
    experts = {(e["layer"], e["expert"]): e for e in index["experts"]}
    schedule = []
    offsets = set()
    wfile = a.new_output_dir / "windows.tsv"
    with wfile.open("x") as out:
        for v, (site, paid) in enumerate(visits):
            callbacks = []
            for ix, key, held in paid:
                job = native["P97"]["jobs"][ix]
                other = native["P106"]["jobs"][ix]
                layer, _, _, expert = job[0]
                need(
                    other[:2] == job[:2]
                    and job[1][:3] == [2, *site]
                    and key == layer * 128 + expert,
                    "service generation",
                )
                cb = indices[tuple(job[1])]
                part = experts[layer, expert]
                off = part["pack_offset"]
                mats = part["components"][:3]
                need(
                    off % 4096 == 0
                    and [m["packed_relative_offset"] for m in mats] == [0, 4406400, 8812800]
                    and all(m["size_bytes"] == 4406400 and m["type"] == "mxfp4" for m in mats),
                    "pack layout",
                )
                print(v, cb, held, off, *(m["sha256"] for m in mats), sep="\t", file=out)
                callbacks.append((cb, held))
                offsets.add(off)
            dispatch = [0, 0]
            for _, rows in groupby(callbacks, key=lambda row: row[0]):
                flags = [b for _, b in rows]
                for i in range(0, len(flags), 4):
                    chunk = flags[i : i + 4]
                    dispatch[0] += 1
                    dispatch[1] += int(not all(chunk))
            schedule.append(
                dict(
                    site=list(site),
                    served=len(paid),
                    seed=sum(h for _, _, h in paid),
                    dispatch=dispatch,
                )
            )
    need(
        sum(v["served"] for v in schedule) == 71 and sum(v["seed"] for v in schedule) == 11,
        "enrolled cohort size",
    )
    stats = {key: [manifest[key][f] for f in M["STAT"]] for key in ("model_stat", "pack_stat")}
    return dict(
        windows=sha(wfile),
        visits=schedule,
        capacity=cap,
        unique=len(offsets),
        model=manifest["model_sha256"],
        pack=manifest["pack_sha256"],
        index=manifest["index_sha256"],
        model_path=manifest["model_path"],
        pack_path=manifest["pack_path"],
        **stats,
    )


def build(a):
    prefix = (T["IO"] / "reader.cpp.in").read_text().split("static auto work_file(")[0]
    return M["build"](a, reader_source=prefix + (HERE / "visit.cpp.in").read_text())


def parse(lines, plan):
    need(
        lines[0].split() == ["fd", *map(str, plan["pack_stat"])]
        and lines[-1] == "drained"
        and lines[1].split() == ["parity", str(plan["unique"])]
        and len(lines) == 39,
        "FD, parity or drain",
    )
    arms = []
    for i, hold in enumerate((0, 1, 1, 0)):
        group = []
        for v, spec in enumerate(plan["visits"]):
            kind, *rest = lines[2 + 9 * i + v].split()
            arm, site, seed, reads, served, dispatch, prepare, ns = map(int, rest)
            need(
                kind == "visit"
                and (arm, site, seed, served) == (i + 1, v, spec["seed"], spec["served"])
                and reads == served - hold * seed
                and dispatch == spec["dispatch"][hold]
                and min(prepare, ns) > 0,
                "visit delivery, incomplete batch or clock",
            )
            group.append(
                dict(
                    site=site,
                    reads=reads,
                    delivered=served,
                    seed=seed,
                    dispatches=dispatch,
                    seed_ns=prepare,
                    wall_ns=ns,
                )
            )
        arms.append(group)
    return dict(
        parity_records=plan["unique"],
        matrix_sha256_comparisons=3 * plan["unique"],
        delivered_markers=9 * 71 * 4,
        initial_markers=9 * 11 * 4,
        arms=arms,
    )


def requested(timing, _plan):
    return timing["parity_records"] + sum(
        v["reads"] + v["seed"] for arm in timing["arms"] for v in arm
    )


def physical(a, receipt):
    window = verified(a.c55 / "receipt.json", a.c55_sha256)
    device = Path("/sys/class/nvme/nvme0")

    def link():
        return [
            (device / "device" / name).read_text().strip()
            for name in ("current_link_speed", "current_link_width")
        ]

    before = link()
    need(
        before == ["16.0 GT/s PCIe", "4"]
        and window["model_device"].split("[")[0] == "/dev/nvme0n1p3",
        "NVMe device or link",
    )
    LEGACY["run"](
        a,
        receipt,
        protocol=METHOD,
        source=HERE / "visit-protocol.md",
        parse=parse,
        maximum_bytes=10 << 30,
        requested_records=requested,
    )
    receipt["status"] = "FAIL_PRESERVED"
    need(link() == before, "changed NVMe link")
    receipt.update(
        pcie=before, nvme_model=(device / "model").read_text().strip(), status="MEASURED"
    )


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "physical":
        del sys.argv[1]
        LEGACY["main"](physical)
        return
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="action", required=True)
    for name, fields in (("plan", ("manifest",)), ("build", ("previous", "rpm"))):
        parser = sub.add_parser(name)
        for field in (*fields, "new-output-dir"):
            parser.add_argument("--" + field, required=True, type=lambda s: Path(s).resolve())
    a = cli.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        commit, tree = M["B"]["version"]()
        need(sha(HERE / "visit-protocol.md") == METHOD, "protocol")
        value = (plan if a.action == "plan" else build)(a)
        save(
            a.new_output_dir / "receipt.json",
            dict(
                status="PASS",
                commit=commit,
                tree=tree,
                protocol=METHOD,
                driver=sha(Path(__file__)),
                **value,
            ),
        )
    except Exception as exc:
        save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise


if __name__ == "__main__":
    main()
