"""Price immutable expert records at actual C281 consumer barriers in a single clock."""

import argparse
import gzip
import json
import os
from collections import Counter, deque
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
P = run_path(HERE.parent / "publications.py")
SRC, need, sha, save, verified = (P[k] for k in ("SRC", "need", "sha", "save", "verified"))
EVIDENCE = HERE.parent / "evidence-20261128-r01"
PRIOR = "094357dd83bfc767cd7f1350e03b5c3ed5d47ddeac03e736fc086d4b3ce1d1ac"
DEST = (14, 14, 7, 54)
TARGET = (2, 5, 14)
WINDOW = 13_221_888
SLAB = 4_406_400


def cut_price(wait, chosen):
    start, end, jobs = wait
    actual = max([start] + [pub for _, _, pub in jobs])
    ideal = max([start] + [res if tuple(key) in chosen else pub for key, res, pub in jobs])
    need(start <= ideal <= actual <= end, "published outside its consumer barrier")
    return actual - ideal


def grade(trace):
    keys = {tuple(k) for k in trace["cohort"]}
    prices = {}
    waits = trace["waits"]
    all_keys = {tuple(k) for _, _, _, jobs in waits for k, _, _ in jobs}
    for label, choices in (("one", {DEST}), ("entry", keys), ("all", all_keys)):
        gains = []
        for site, *wait in waits:
            gain = cut_price(wait, choices)
            if gain:
                gains.append([site, gain])
        prices[label] = dict(
            positive=len(gains),
            sum_ns=sum(g for _, g in gains),
            max_ns=max((g for _, g in gains), default=0),
            target=[[s, g] for s, g in gains if tuple(s[:3]) == TARGET],
        )
    need(len(keys) == 75 and len(waits) == 1296, "published barrier and cohort population")
    return prices


def collect(rows, entry):
    bindings = SRC["Q"]["bindings"](rows)
    live = {
        (layer, s): (layer, s, gen, e)
        for (layer, s), (e, gen, state, claimed) in bindings.items()
        if state == 2 and claimed == 0
    }
    need(len(live) == 1440, "initial resident pools")
    pubs = dict.fromkeys(live.values(), 0)
    src = next(
        (v["layer"], v["slot"], v["generation"], v["expert"])
        for v in entry
        if (v["layer"], v["expert"]) == (14, 54)
    )
    cohort = {(v["layer"], v["expert"]) for v in entry}
    pending = {}
    reserve = {}
    queue = deque()
    active = {}
    counts = Counter()
    waves = {}
    parking = {}
    previous_pin = None
    owner_events = []
    cut = None
    trace = []
    records = []
    waits = []
    selected = set()
    victim_waits = []
    started = None
    barrier = None
    target_initial = None
    max_active = 0
    for r in rows:
        if r.kind == 1 and r.call > 2:
            break
        k = SRC["key"](r)
        site = SRC["origin"](r)
        is_target = site[:3] == TARGET
        if r.call == 2:
            counts[r.kind] += 1
        if r.kind == 1 and r.call == 2:
            need(not queue and not active and live[src[:2]] == src, "generation on entry")
            cut = r.ns
        if is_target and r.kind in (9, 10, 11, 12, 13, 14, 16, 17, 19, 20, 21, 22, 23, 27, 30):
            trace.append(
                [
                    r.kind,
                    r.wave,
                    r.expert,
                    r.slot,
                    r.gen,
                    r.worker,
                    r.component,
                    r.a,
                    r.b,
                    r.begin,
                    r.ns,
                ]
            )
        if r.kind == 9:
            need(started is None, "overlapping graph callbacks")
            started = site
            waves[site] = []
            if is_target and site[3] == 0:
                need(not queue and not active, "foreign work at layer entry")
                target_initial = [list(live[14, j]) for j in range(40)]
        elif r.kind == 11:
            old = live[k[:2]]
            need(old[2:] == (k[2] - 1, r.a) and k not in reserve, "victim generation")
            if k[:2] == src[:2] and r.call == 2:
                owner_events.append(
                    dict(site=site, old=old, new=k, ns=r.ns, previous_source_pin=previous_pin)
                )
            live[k[:2]] = k
            reserve[k] = (site, r.ns)
            if r.call == 2 and (k[0], k[3]) in cohort:
                selected.add(k)
        elif r.kind == 12:
            need(k in reserve and (r.a == 1 or reserve[k][0] == site), "queue origin")
            queue.append(k)
        elif r.kind in (13, 14):
            need(queue and queue.popleft() == k and 0 <= r.worker < 4, "FIFO or worker")
            if r.kind == 13:
                need(r.worker not in active and k not in pending and k not in pubs, "worker claim")
                active[r.worker] = k
                pending[k] = []
                max_active = max(max_active, len(active))
            else:
                need(k in pending or k in pubs, "unexplained duplicate skip")
        elif r.kind in (30, 16, 17):
            need(active.get(r.worker) == k, "service by unexpected worker")
            events = pending[k]
            if r.kind == 30:
                need(not events and not r.error and r.b == r.c == WINDOW, "packed read")
            elif r.kind == 16:
                need(
                    len(events) == 1 + r.component
                    and 0 <= r.component < 3
                    and r.a == SLAB
                    and not r.error
                    and events[-1] <= r.begin,
                    "ordered component",
                )
            else:
                need(len(events) == 4 and events[-1] <= r.ns and live[k[:2]] == k, "publication")
                pubs[k] = r.ns
                del active[r.worker]
                del pending[k]
            events.append(r.ns)
        elif r.kind == 10:
            need(
                started == site and live[k[:2]] == k and k not in waves[site],
                "stale or duplicate pin",
            )
            waves[site].append(k)
        elif r.kind == 19:
            need(barrier is None and started == site, "overlapping demand waits")
            barrier = (site, r.ns, [k for k in waves[site] if k not in pubs])
        elif r.kind == 20:
            need(
                barrier and barrier[0] == site and all(k in pubs for k in waves[site]),
                "unready wave",
            )
            _, start, unfinished = barrier
            if r.call == 2:
                need(not waits or waits[-1][2] <= start, "overlapping clock intervals")
                eligible = [[list(k), reserve[k][1], pubs[k]] for k in unfinished]
                need(
                    all(res <= start <= pub <= r.ns for _, res, pub in eligible), "readiness clock"
                )
                waits.append([list(site), start, r.ns, eligible])
            barrier = None
        elif r.kind in (21, 22):
            victim_waits.append([r.kind, site, r.ns])
        elif r.kind == 23:
            need(started == site and barrier is None, "unmatched graph return")
            pins = waves[site]
            if site[3] >= 0:
                add = max(0, 4 - len(pins))
                borrowed = parking.get(r.layer, [])[:add]
                need(
                    len(borrowed) == add
                    and all(live[k[:2]] == k for k in borrowed)
                    and set(borrowed).isdisjoint(pins),
                    "borrowed parking generation",
                )
                parking[r.layer] = pins + borrowed
                if src in pins or src in borrowed:
                    previous_pin = [list(site), "demand" if src in pins else "parking", r.ns]
            elif src in pins:
                previous_pin = [list(site), "demand", r.ns]
            if is_target:
                records.append(
                    [
                        list(site),
                        [list(key) for key in pins],
                        [list(key) for key in parking[r.layer]],
                    ]
                )
            started = None
        elif r.kind == 2:
            need(not queue and not active and not pending and started is None, "incomplete return")
    need(
        cut is not None
        and counts[11] == counts[13] == counts[17] == counts[30] == 1212
        and counts[16] == 3636
        and counts[12] == counts[13] + counts[14]
        and counts[9] == counts[19] == counts[20] == counts[23] == 1296
        and max_active == 4
        and not (counts[18] or counts[28])
        and not victim_waits,
        "conservation or unpriced victim wait",
    )
    need(
        target_initial and owner_events and owner_events[0]["old"] == src and DEST in selected,
        "source history or destination",
    )
    return dict(
        waits=waits,
        cohort=sorted(selected),
        counts=dict(sorted(counts.items())),
        max_active=max_active,
        call_start=cut,
        source=src,
        replacements=owner_events,
        source_final=live[src[:2]],
        destination_final=live[DEST[:2]],
        site_initial=target_initial,
        site_events=trace,
        site_pins=records,
        victim_waits=victim_waits,
    )


def packed(v):
    return gzip.compress(json.dumps(v, sort_keys=True, separators=(",", ":")).encode(), mtime=0)


def obtain(archive, build):
    old = verified(EVIDENCE / "publications.json", PRIOR)
    entry = verified(build / "receipt.json", P["BUILD"])["plan"]["records"]
    traces = {}
    for tag, seal in old["sources"].items():
        name, h, _ = SRC["SOURCES"][tag]
        root = archive / ("part-" + tag[1:]) / name
        file = root / ("ON/raw/events.pfj" if tag == "P97" else "ON/observer/events.pfj")
        need(sha(file) == seal, "journal identity")
        if tag == "P97":
            rows, _ = SRC["T"]["PFJ"]["read_journal"](file)
        else:
            _, rows, _, _ = SRC["Q"]["read_new"](root, h)
        traces[tag] = collect(rows, entry)
        del rows
    return dict(traces=traces, sources=old["sources"], build=P["BUILD"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path)
    p.add_argument("--build", type=Path)
    dest = p.add_mutually_exclusive_group(required=True)
    dest.add_argument("--new-output-dir", type=Path)
    dest.add_argument("--check", type=Path)
    a = p.parse_args()
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        if a.check:
            data = json.loads(gzip.decompress((a.check / "waits.json.gz").read_bytes()))
        else:
            data = obtain(a.archive, a.build)
        prior = verified(EVIDENCE / "publications.json", PRIOR)
        need(data["sources"] == prior["sources"] and data["build"] == P["BUILD"], "sealed inputs")
        prices = {k: grade(v) for k, v in data["traces"].items()}
        status = (
            "GO_QUEUE_FIXTURE" if all(v["one"]["sum_ns"] > 0 for v in prices.values()) else "NO_GO"
        )
        out = a.check or a.new_output_dir
        if not a.check:
            (out / "waits.json.gz").write_bytes(packed(data))
        receipt = dict(
            status=status,
            grade=prices,
            waits=sha(out / "waits.json.gz"),
            source=sha(Path(__file__)),
            protocol=sha(HERE / "protocol.md"),
            parent=PRIOR,
            evidence="TRACE_DERIVED_FIXED_PEERS",
            model_forwards=0,
        )
        if a.check:
            need(receipt == json.loads((out / "wait-grade.json").read_bytes()), "public audit")
        else:
            save(out / "wait-grade.json", receipt)
        print(
            status,
            {k: {p: (r["positive"], r["sum_ns"]) for p, r in v.items()} for k, v in prices.items()},
        )
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise


if __name__ == "__main__":
    os.umask(0o077)
    main()
