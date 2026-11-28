"""Bound disk interference at the actual target generations and consumer regions."""

import argparse
import gzip
import json
import os
from collections import Counter, defaultdict, deque
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / "evidence-20261128-r01"
C = run_path(HERE.parent / "causal.py")
SRC, need, sha, save = (C[k] for k in ("SRC", "need", "sha", "save"))
METHOD = "44163ffcd63410e5e8baaf0d1921e2cc8f960f1013abc00abd44e12971564a96"
OLD = "5dd9d771a5c446965832c499dccf268bc39925d0da8a80e386b4d7eb37adcdbf"
WINDOW = C["stride"]
SLAB = C["OBS"]["SLAB"]


def unpack(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def freeze():
    provenance = json.loads((PARENT / "provenance.json").read_bytes())
    for name in ("causal-input.json.gz", "causal-grade.json", "arms.json.gz", "waits.json.gz"):
        need(sha(PARENT / name) == provenance["artifacts"][name], "previous input " + name)
    basis = unpack(PARENT / "causal-input.json.gz")
    previous = SRC["pinned"](PARENT / "causal-grade.json", OLD)
    return basis, previous, unpack(PARENT / "arms.json.gz")


def collect(rows):
    waves, origins = SRC["timeline"](rows)
    need(len(waves) == 2987 and len(origins) == 2354, "complete callbacks and generations")
    jobs = {}
    queue = deque()
    active = {}
    barrier = None
    last = []
    demands = []
    for e in rows:
        key = SRC["key"](e)
        if e.kind == 9:
            demands = []
        elif e.kind == 10:
            demands.append(key)
        elif e.kind == 11:
            need(key not in jobs and SRC["origin"](e) == origins[key], "generation and origin")
            jobs[key] = [list(key), list(origins[key]), e.ns]
        elif e.kind == 12:
            queue.append(key)
        elif e.kind in (13, 14):
            need(queue and queue.popleft() == key and e.worker in range(4), "FIFO or worker")
            if e.kind == 13:
                need(e.worker not in active and len(jobs[key]) == 3, "native claim")
                jobs[key].extend([e.worker, e.ns])
                active[e.worker] = key
        elif e.kind in (30, 16, 17):
            j = jobs[key]
            need(active.get(e.worker) == key, "wrong worker")
            if e.kind == 30:
                need(len(j) == 5 and e.b == e.c == WINDOW and not e.error, "aligned read")
                j.extend([e.begin, e.ns])
            elif e.kind == 16:
                need(
                    len(j) == 7 + 2 * e.component
                    and e.component in range(3)
                    and e.a == SLAB
                    and not e.error,
                    "SET sequence",
                )
                j.extend([e.begin, e.ns])
            else:
                need(len(j) == 13, "publication before all components")
                j.append(e.ns)
                del active[e.worker]
        elif e.kind == 19:
            need(barrier is None, "nested consumer")
            barrier = (e.ns, list(demands), SRC["origin"](e))
        elif e.kind == 20:
            start, pins, site = barrier
            need(site == SRC["origin"](e), "consumer identity")
            publications = []
            for k in pins:
                if k in jobs:
                    j = jobs[k]
                    need(len(j) == 14 and j[-1] <= e.ns, "unpublished consumer")
                    if j[-1] > start:
                        publications.append((j[-1], k))
            if publications:
                t, _ = max(publications)
                # Inclusive of ties between publications with nanosecond resolution.
                last.append(
                    [list(site), start, e.ns, [list(k) for when, k in publications if when == t]]
                )
            barrier = None
    need(not active and not queue and not barrier and len(jobs) == 2354, "terminal drain")
    return dict(jobs=list(jobs.values()), last=last)


def intervals(ranges):
    merged = []
    for a, b in sorted(ranges):
        need(a <= b, "inverted interval")
        if a == b:
            continue
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


def overlap(a, b, merged):
    return sum(max(0, min(b, y) - max(a, x)) for x, y in merged)


def verify_jobs(rows, arm):
    clocks = {
        i: (r, s, num)
        for num, groups, _, _ in arm["regions"]
        for _, _, jobs in groups
        for i, r, s in jobs
    }
    need(len(rows) == len(clocks) == 2354, "job coverage")
    occupancy = defaultdict(list)
    names = {}
    for i, (key, site, reserve, worker, claim, rb, re, *tail) in enumerate(rows, 1):
        need(tuple(key) not in names and worker in range(4) and len(tail) == 7, "generation")
        names[tuple(key)] = i
        ticks = [reserve, claim, rb, re, *tail]
        need(ticks == sorted(ticks) and re > rb, "ordered service, worker or publication")
        need(
            clocks[i] == (re - rb, sum(tail[z + 1] - tail[z] for z in (0, 2, 4)), site[0]),
            "complete original prices",
        )
        occupancy[worker].append((claim, tail[-1]))
    for work in occupancy.values():
        ordered = sorted(work)
        need(
            all(a[1] <= b[0] for a, b in zip(ordered, ordered[1:], strict=False)),
            "overlapping worker claims",
        )
    need(len(occupancy) == 4, "four workers")
    return names


def choices(basis, tag, previous, captures):
    arm = basis["arms"][tag]
    sets = {"off": set(), "entry": set()}
    keys = []
    call = 0
    for op, k in arm["events"]:
        if op == 1:
            call = k
        elif op == 11:
            keys.append(k)
            if call == 2 and k in captures:
                sets["entry"].add(len(keys))
    need(len(sets["entry"]) == 70 and len(keys) == 2354, "physical cohort")
    for cap in (69, 353):
        bank = C["Bank"](cap, True)
        bank.replay(basis["t1"], training=True)
        hits, _ = bank.replay(arm["events"])
        name = f"frequency_{cap}"
        need(
            C["IV"]["digest"](sorted(hits)) == previous["policy"][name]["arms"][tag]["hits_sha256"],
            "causal choices",
        )
        sets[name] = hits
    return sets, keys


def quartets(rows, hits):
    live = {}
    witnesses = set()
    for i, j in sorted(enumerate(rows, 1), key=lambda item: (item[1][5], item[0])):
        live = {idx: z for idx, z in live.items() if z[6] > j[5]}
        live[i] = j
        need(len(live) <= 4, "more than four simultaneous READ")
        selected = live.keys() & hits
        if (
            len(live) == 4
            and len(selected) == 1
            and j[1][0] == 2
            and j[0][0] < 25
            and all(v[1][:3] == j[1][:3] for v in live.values())
        ):
            (hit,) = selected
            witnesses.add((hit, *sorted(live.keys() - selected)))
    return witnesses


def adjusted(arm, read_credit, free_set=()):
    changed = []
    for num, groups, edges, discount in arm["regions"]:
        new = []
        for inside, placed, jobs in groups:
            costs = []
            for i, r, s in jobs:
                cut = read_credit.get(i, 0)
                need(0 <= cut <= r, "READ credit exceeds work")
                costs.append([i, r - cut, 0 if i in free_set else s])
            new.append([inside, placed, costs])
        changed.append([num, new, edges, discount])
    return arm | {"regions": changed}


def clock(arm, hits, placed, free, tag):
    obs = C["price"](arm, hits, placed, free)
    credit = C["CC"]["CREDIT"] if placed and tag == "P106" else 0
    return obs | {
        "client_credit_ns": credit,
        "granted_first_ns": obs["first_final"] - credit,
        "joint_margin_with_credit_ns": min(
            obs["margin_ns"]["first_final"] + credit, obs["margin_ns"]["decode"]
        ),
    }


def threshold(arm, hits, jobset, rows, tag):
    # Keep SET free on the eligible class. This is the most generous registered test.
    peers = jobset - hits

    def fits(ppm):
        cut = {i: (rows[i - 1][6] - rows[i - 1][5]) * (1_000_000 - ppm) // 1_000_000 for i in peers}
        return (
            clock(adjusted(arm, cut, peers), hits, True, True, tag)["joint_margin_with_credit_ns"]
            >= 0
        )

    if not fits(0):
        return {"status": "NO_GO_FREE_ELIGIBLE_SERVICE"}
    lo, hi = 0, 1_000_001
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if fits(mid):
            lo = mid
        else:
            hi = mid
    need(fits(lo) and (hi > 1_000_000 or not fits(hi)), "break-even endpoints")
    return dict(max_peer_read_ppm=lo, min_peer_read_reduction_ppm=1_000_000 - lo)


def assess(arm, obs, hits, names, tag, do_threshold):
    rows = obs["jobs"]
    hit_union = intervals((rows[i - 1][5], rows[i - 1][6]) for i in hits)
    regions = {tuple(rows[i - 1][1][:3]) for i in hits}
    cut = {}
    zone = set(hits)
    account = defaultdict(Counter)
    for i, j in enumerate(rows, 1):
        a = account[C["phase"](j[1][0])]
        a["reserved"] += 1
        if tuple(j[1][:3]) in regions:
            zone.add(i)
        if i in hits:
            a["hits"] += 1
        else:
            a["misses"] += 1
            v = overlap(j[5], j[6], hit_union)
            if v:
                cut[i] = v
                a.update(touching_misses=1, shared_worker_ns=v, whole_peer_read_ns=j[6] - j[5])
                zone.add(i)
    for i in zone:
        account[C["phase"](rows[i - 1][1][0])]["region_or_simultaneous"] += 1
    touching = hits | cut.keys()
    for site, start, end, keys in obs["last"]:
        ids = {names[tuple(k)] for k in keys}
        need(all(start < rows[i - 1][-1] <= end for i in ids), "charged last dependency")
        a = account[C["phase"](site[0])]
        a.update(
            exposed_barriers=1,
            last_hit=int(bool(ids & hits)),
            last_peer=int(bool(ids & cut.keys())),
            all_last_in_region=int(ids <= zone),
        )
    clocks = dict(
        direct=clock(arm, hits, False, False, tag),
        overlap_only=clock(adjusted(arm, cut), hits, False, False, tag),
        whole_peer_read=clock(arm, touching, False, False, tag),
        generous_peers=clock(arm, touching, True, True, tag),
        generous_regions=clock(arm, zone, True, True, tag),
    )
    values = list(clocks.values())
    need(
        all(
            v["granted_first_ns"] <= u["granted_first_ns"] and v["decode"] <= u["decode"]
            for u, v in zip(values, values[1:], strict=False)
        ),
        "grants must nest",
    )
    limits = {}
    if do_threshold:
        for scope, eligible in (("peers", touching), ("regions", zone)):
            limits[scope] = threshold(arm, hits, eligible, rows, tag)
    return dict(
        phases=account,
        clocks=clocks,
        limits=limits,
        hit_read_wall_union_ns=sum(b - a for a, b in hit_union),
    )


def grade(data):
    basis, old, arms = freeze()
    captures = {c[0] for c in arms[1]["captures"]}
    result = {}
    cohorts = None
    rows_ref = None
    for tag, obs in data.items():
        arm = basis["arms"][tag]
        rows = obs["jobs"]
        names = verify_jobs(rows, arm)
        sets, keys = choices(basis, tag, old, captures)
        identities = [j[0] for j in rows]
        need(
            all(128 * k[0] + k[3] == code for k, code in zip(identities, keys, strict=True))
            and (rows_ref is None or rows_ref == identities),
            "same ordinal and physical generation",
        )
        rows_ref = identities
        current = quartets(rows, sets["frequency_353"])
        cohorts = current if cohorts is None else cohorts & current
        result[tag] = {
            name: assess(arm, obs, hits, names, tag, name == "frequency_353")
            for name, hits in sets.items()
        }
        for name in ("off", "frequency_69", "frequency_353"):
            expect = old["policy"]["off_0" if name == "off" else name]["arms"][tag]["paid"]
            need(
                all(result[tag][name]["clocks"]["direct"][k] == v for k, v in expect.items()),
                "previous client clocks",
            )
    need(set(result) == {"P97", "P106"}, "independent journals")
    physical = [14 * 128 + e for e in (94, 29, 107, 54)]
    for role in ("o1", "o2"):
        arm = next(a for a in arms if a["role"] == role)
        j = {r["reservation"][0]: r for r in arm["jobs"]}
        a, b = j[54]["read"]
        need(
            all(j[k]["read"][0] <= a < j[k]["read"][1] for k in (94, 29, 107)) and a < b,
            "historical overlap",
        )
    cohorts = sorted(cohorts)
    selected = {"physical_54": physical}
    ordinal = None
    if cohorts:
        hit, *peers = cohorts[0]
        ordinal = [*peers, hit]
        selected["causal_353"] = [128 * rows_ref[i - 1][0] + rows_ref[i - 1][3] for i in ordinal]
    return dict(
        evidence="TRACE_DERIVED_CONDITIONAL",
        method=METHOD,
        arms=result,
        common_quartets=len(cohorts),
        groups=selected,
        causal_ordinals=ordinal,
        decisions={
            name: (
                "NO_GO_EVEN_FREE_REGION_SERVICE"
                if any(
                    result[tag][name]["clocks"]["generous_regions"]["joint_margin_with_credit_ns"]
                    < 0
                    for tag in result
                )
                else "NO_GO_SIMULTANEOUS_ONLY"
                if any(
                    result[tag][name]["clocks"]["generous_peers"]["joint_margin_with_credit_ns"] < 0
                    for tag in result
                )
                else "HEADROOM_ONLY"
            )
            for name in result["P97"]
        },
    )


def obtain(archive):
    basis, _, _ = freeze()
    out = {}
    for tag, arm in basis["arms"].items():
        name, outer, _ = SRC["SOURCES"][tag]
        root = archive / ("part-" + tag[1:]) / name
        if tag == "P106":
            file = root / "ON/observer/events.pfj"
            _, rows, _, _ = SRC["Q"]["read_new"](root, outer)
        else:
            file = root / "ON/raw/events.pfj"
            rows, _ = SRC["T"]["PFJ"]["read_journal"](file)
        need(sha(file) == arm["journal_sha256"], "journal digest")
        out[tag] = collect(rows)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path)
    dest = p.add_mutually_exclusive_group(required=True)
    dest.add_argument("--new-output-dir", type=Path)
    dest.add_argument("--check", type=Path)
    args = p.parse_args()
    os.umask(0o077)
    need(sha(HERE / "protocol.md") == METHOD, "registered protocol")
    if args.check:
        got = grade(unpack(args.check / "service.json.gz"))
        need(
            got == json.loads((args.check / "frontier.json").read_bytes()),
            "public cost reproduction",
        )
    else:
        out = args.new_output_dir
        out.mkdir()
        try:
            data = obtain(args.archive)
            got = grade(data)
            save(out / "service.json.gz", data)
            save(out / "frontier.json", got)
        except Exception as exc:
            missing = (
                isinstance(exc, FileNotFoundError)
                and exc.filename is not None
                and Path(exc.filename).resolve().is_relative_to(args.archive.resolve())
            )
            save(
                out / "failure.json",
                dict(
                    status="NOT_RUN_RAW_REQUIRED" if missing else "FAIL_PRESERVED", reason=repr(exc)
                ),
            )
            raise
    print(got["decisions"], got["groups"])


if __name__ == "__main__":
    main()
