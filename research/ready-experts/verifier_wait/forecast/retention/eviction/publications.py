"""Identify whether the 75 live primary-record hits published the last weights in C281."""

import argparse
import os
from collections import defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
U = run_path(HERE / "consumer_build.py")
S, need, sha, save, verified, F = (U[k] for k in ("S", "need", "sha", "save", "verified", "F"))
SRC = U["E"]["T"]["SRC"]
BUILD = "dd2067917d32c970d645fee0f622f194e2a0fce422032d0b6de541fca62ff1b1"


def collect(rows, jobs, keys):
    times = {}
    sites = defaultdict(list)
    for r in rows:
        k = SRC["key"](r)
        if r.kind == 11 and r.call == 2:
            need(
                k in jobs and jobs[k] == (r.call, r.tile, r.layer) and k not in times,
                "native generation",
            )
            times[k] = [r.ns, None, [], None]
        if k not in times or r.kind not in (30, 16, 17):
            continue
        t = times[k]
        if r.kind == 30:
            need(
                t[1] is None and not r.error and t[0] <= r.begin < r.ns and r.b == r.c == 13221888,
                "READ",
            )
            t[1] = r.ns
        elif r.kind == 16:
            need(
                t[1] is not None
                and r.component == len(t[2]) < 3
                and r.a == 4406400
                and (t[2][-1] if t[2] else t[1]) <= r.begin < r.ns,
                "ordered SET",
            )
            t[2].append(r.ns)
        else:
            need(len(t[2]) == 3 and t[2][-1] <= r.ns and t[3] is None, "publication")
            t[3] = r.ns
            layer, _, _, expert = k
            sites[jobs[k]].append([*k, int((layer, expert) in keys), t[0], r.ns])
    need(
        times.keys() == jobs.keys() and all(t[3] is not None for t in times.values()),
        "all 1212 generations",
    )
    affected = [[*site, sorted(v)] for site, v in sorted(sites.items()) if any(a[-3] for a in v)]
    need(
        sum(sum(row[-3] for row in group) for *_, group in affected) == 75,
        "all 75 selected occurrences",
    )
    return affected


def grade(groups):
    leads = []
    exclusive = 0
    candidates = jobs = last = 0
    for _, _, _, group in groups:
        selected = [r for r in group if r[-3]]
        other = [r for r in group if not r[-3]]
        need(selected and all(r[-2] <= r[-1] for r in group), "time order")
        final = max(r[-1] for r in group)
        always = max(r[-2] for r in selected)
        other_latest = max((r[-1] for r in other), default=always)
        leads.append(final - max(always, other_latest))
        jobs += len(group)
        candidates += len(selected)
        last += int(all(r[-1] < final for r in other))
        exclusive += int(not other)
    need(candidates == 75 and len(groups) == len({tuple(g[:3]) for g in groups}), "selected cohort")
    return dict(
        sites=len(groups),
        selected=candidates,
        all_jobs_at_these_sites=jobs,
        all_selected_sites=exclusive,
        last_selected_sites=last,
        unchanged_peer_last_sites=len(groups) - last,
        local_leads_ns=leads,
        sum_fixed_peer_publication_lead_ns=sum(leads),
        maximum_site_lead_ns=max(leads),
    )


def obtain(a):
    verified_inputs = verified(a.build / "receipt.json", BUILD)
    keys = {(v["layer"], v["expert"]) for v in verified_inputs["plan"]["records"]}
    parent = verified(F["CONTROL"], F["CONTROL_SHA"])
    tx = verified(S["PATHS"]["transactions"], parent["inputs"]["transactions"])
    jobs = {
        (layer, slot, gen, e): (c, t, layer)
        for c, t, layer, slot, gen, e, _ in tx["reservations"]
        if c == 2
    }
    need(len(keys) == 74 and len(jobs) == 1212, "source read census")
    layout = verified(U["E"]["T"]["E"] / "layout.json", U["E"]["R"]["CONFIG"]["layout"])
    groups = {}
    seals = {}
    for tag in ("P97", "P106"):
        name, h, _ = SRC["SOURCES"][tag]
        root = a.archive / ("part-" + tag[1:]) / name
        file = root / ("ON/raw/events.pfj" if tag == "P97" else "ON/observer/events.pfj")
        seals[tag] = sha(file)
        need(seals[tag] == layout["arms"][tag]["journal_sha256"], "authentic C281")
        if tag == "P97":
            rows, _ = SRC["T"]["PFJ"]["read_journal"](file)
        else:
            _, rows, _, _ = SRC["Q"]["read_new"](root, h)
        groups[tag] = collect(rows, jobs, keys)
        del rows
    return dict(groups=groups, sources=seals)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path)
    p.add_argument("--build", type=Path)
    dest = p.add_mutually_exclusive_group(required=True)
    dest.add_argument("--check", type=Path)
    dest.add_argument("--new-output-dir", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        if a.check:
            data = F["load"](a.check)
        else:
            data = obtain(a)
        stats = {tag: grade(groups) for tag, groups in data["groups"].items()}
        need(set(stats) == {"P97", "P106"}, "separate journal clocks")
        layout = verified(U["E"]["T"]["E"] / "layout.json", U["E"]["R"]["CONFIG"]["layout"])
        need(
            data["sources"] == {t: layout["arms"][t]["journal_sha256"] for t in stats},
            "source journal seals",
        )
        if a.check:
            need(
                stats == data["grading"]
                and data["program"] == sha(Path(__file__))
                and data["protocol"] == sha(HERE / "publications.md")
                and data["build"] == BUILD,
                "public audit",
            )
        else:
            save(
                a.new_output_dir / "receipts.json",
                data
                | dict(
                    grading=stats,
                    protocol=sha(HERE / "publications.md"),
                    program=sha(Path(__file__)),
                    build=BUILD,
                    evidence="TRACE_DERIVED_FIXED_PEER_TIMES",
                ),
            )
        print(
            [
                (k, v["last_selected_sites"], v["sites"], v["sum_fixed_peer_publication_lead_ns"])
                for k, v in stats.items()
            ]
        )
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise


if __name__ == "__main__":
    main()
