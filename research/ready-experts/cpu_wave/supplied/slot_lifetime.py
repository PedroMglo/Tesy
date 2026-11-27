"""Replay physical CPU slot lifetimes and wave deadlines on the two authenticated T2s."""

import argparse
import gzip
import itertools
import json
import os
import subprocess
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
FR = run_path(HERE / "frontier.py")
L, sha, need, limits = (FR[k] for k in ("L", "sha", "need", "limits"))
METHOD = "dbc8ac2fab33d1ec5ef9197a8886e95b2ebbdc09d7294fd8eb4ff56909201ab3"
PARENT = "02beb453cbc65d6d481a45c5f7faae51cc39f27dcfc64a5539735c1a6ea0bdc8"
SIZE = 13_219_200


@dataclass(frozen=True)
class Job:
    order: int
    key: tuple
    region: int
    horizon: int  # opening wave of the earliest region available to the oracle
    reserve: int
    due: int
    old_use: int  # last real demand of the victim in this call, or -1
    old_pin: int  # also protects borrowed parking positions until their wave finishes
    read: int
    put: int

    @property
    def cpu(self):
        return self.key[0] < 25


def ledger(rows, src, primary):
    groups, prices = primary["packed_groups"](rows)
    live = {p: (p[0], p[1], gen, e) for p, (e, gen, _, _) in src["Q"]["bindings"](rows).items()}
    need(len(live) == 1440 and all(k[3] >= 0 for k in live.values()), "initial slot snapshot")
    initial = set(live.values())
    parking, uses, pins, due, ids = {}, {}, {}, {}, {}
    population, records = Counter(), defaultdict(list)
    wave_counts, regions, origin_by_order = {}, {}, []
    for n, items in itertools.groupby(groups, lambda g: g["site"][0]):
        sites, starts, last_region = [], [], None
        for i, group in enumerate(items):
            _, tile, layer, wave = group["site"]
            if (tile, layer) != last_region:
                starts.append(i)
                last_region = tile, layer
            reg = len(starts) - 1
            sites.append(reg)
            for e, slot, gen, victim, reason in group["new"]:
                position = layer, slot
                old = live[position]
                key = (layer, slot, gen, e)
                need(old[2:] == (gen - 1, victim) and key not in ids, "physical victim/generation")
                order = len(origin_by_order)
                origin_by_order.append((n, reg))
                ids[key] = order
                live[position] = key
                read, put = prices[key]
                last_use = uses.get(old, (0, -1))
                last_pin = pins.get(old, (0, -1))
                records[n].append(
                    (
                        order,
                        key,
                        reg,
                        starts[max(0, reg - 2)],
                        i,
                        last_use[1] if last_use[0] == n else -1,
                        last_pin[1] if last_pin[0] == n else -1,
                        read,
                        put,
                    )
                )
                population["preload" if reason == 2 else "demand_reserve"] += 1
                population["cpu_generations" if layer < 25 else "cuda_generations"] += 1
            own = []
            for expert, slot, gen in group["demands"]:
                key = live[layer, slot]
                need(key[2:] == (gen, expert), "stale active consumer")
                due.setdefault(key, (n, i))
                uses[key] = pins[key] = n, i
                own.append(key)
            need(len(set(own)) == len(own), "duplicate active demand")
            population["demand_records"] += len(own)
            if wave >= 0:
                missing = max(0, 4 - len(own))
                borrowed = parking.get(layer, [])[:missing]
                need(len(borrowed) == missing and set(borrowed).isdisjoint(own), "borrowed pool")
                for key in borrowed:
                    need(live[key[:2]] == key, "parking generation overwritten")
                    pins[key] = n, i
                parking[layer] = own + borrowed
                population["borrowed_cpu" if layer < 25 else "borrowed_cuda"] += missing
        regions[n], wave_counts[n] = sites, len(sites)
    native = Counter(e.kind for e in rows)
    need(set(ids) == set(prices) <= set(due) and set(due) <= initial | set(ids), "all consumers")
    need(
        native[11] == native[30] == native[17] == len(ids) == 2354
        and native[16] == 3 * len(ids)
        and native[9] == native[23] == sum(wave_counts.values()) == 2987
        and native[10] == population["demand_records"]
        and not (native[18] or native[28]),
        "original conservation",
    )
    calls = {}
    for n in regions:
        jobs = []
        for order, key, reg, horizon, reserve, old_use, old_pin, read, put in records[n]:
            c, first = due[key]
            need(
                c == n
                and regions[n][first] == reg
                and 0 <= reserve <= first
                and old_use <= old_pin < reserve
                and read > 0
                and put > 0,
                "lifetime, release, first use or service",
            )
            jobs.append(
                Job(
                    order,
                    key,
                    reg,
                    horizon,
                    reserve,
                    first,
                    old_use,
                    old_pin,
                    read,
                    1 if key[0] < 25 else put,
                )
            )
        calls[n] = jobs
    population.update(
        waves=native[9],
        initial_slots=len(initial),
        reads=native[30],
        sets=native[16],
        publications=native[17],
        cancellations=native[28],
    )
    return calls, regions, population


def coarse_audit(groups, jobs, regions):
    keyed = {j.order: j for j in jobs}
    converted = [
        [L["Job"](j.order, j.group, j.read, keyed[j.order].put) for j in g] for g in groups
    ]
    _, _, events = FR["schedule"](converted, 2)
    opening, history = events
    counts, by_slot = Counter(), defaultdict(list)
    for i, _, begin, ready, _, end in history:
        j = keyed[i]
        if not j.cpu:
            continue
        need(j.region == regions[j.reserve] and end <= opening[j.region + 1], "parent region")
        same_use = j.old_use >= 0 and regions[j.old_use] == j.region
        same_pin = j.old_pin >= 0 and regions[j.old_pin] == j.region
        early = begin < opening[j.region]
        counts["early_reads_cpu"] += int(early)
        counts["same_region_old_use"] += int(same_use)
        counts["same_region_old_pin"] += int(same_pin)
        counts["early_before_old_use"] += int(early and same_use)
        counts["early_before_old_pin"] += int(early and same_pin)
        by_slot[j.key[:2]].append((j.key[2], begin, ready, end, j.region))
    for chain in by_slot.values():
        for old, new in itertools.pairwise(sorted(chain)):
            need(new[0] == old[0] + 1, "slot succession")
            counts["successors_same_region"] += int(new[4] == old[4])
            counts["successors_before_old_publish"] += int(new[1] < old[3])
            counts["overlapping_direct_writes"] += int(max(new[1], old[1]) < min(new[2], old[2]))
    return events, counts


def interval_edges(jobs, waves):
    # Node 2w opens wave w. Node 2w+1 joins its mandatory publications before graph work.
    # For a necessary condition, grant release of old CPU bytes as soon as demand is joined.
    by_due = defaultdict(list)
    releases = set()
    for j in jobs:
        read = max(2 * j.horizon, 2 * j.old_use + 1 if j.cpu else 0)
        put = 2 * j.reserve
        need(read <= put <= 2 * j.due, "read/put gate follows mandatory use")
        by_due[2 * j.due + 1].append((read, put, j.read, j.put))
        releases.update((read, put))
    edges = [[] for _ in range(2 * waves + 1)]
    for start in sorted(releases):
        work = single = 0
        for stop, batch in sorted(by_due.items()):
            added = False
            for read, put, read_ns, put_ns in batch:
                cost = (read_ns if read >= start else 0) + (put_ns if put >= start else 0)
                if cost:
                    work += cost
                    single = max(single, cost)
                    added = True
            if added:
                need(stop > start, "backward interval")
                edges[stop].append((start, max(single, (work + 3) // 4)))
    return edges


def graph_floor(entry, gaps, edges, percent):
    times = [0] * (2 * len(gaps) + 1)
    for w, gap in enumerate(gaps):
        join = 2 * w + 1
        ready = max((times[s] + ns for s, ns in edges[join]), default=0)
        times[join] = max(times[join - 1], ready, entry * percent // 100 if w == 0 else 0)
        times[join + 1] = times[join] + gap * percent // 100
    return times[-1]


def schedule(jobs, entry, gaps):
    pending = deque(sorted(jobs, key=lambda j: (j.due, j.order)))
    outstanding = Counter(j.due for j in jobs)
    lanes = [None] * 4
    opening, barriers, history = [entry], [], {}
    now, w = entry, 0
    while w < len(gaps):
        for lane, j in enumerate(lanes):
            if j is None:
                continue
            row = history[j.order]
            if len(row) == 5 and row[-1] == now:
                lanes[lane] = None
                outstanding[j.due] -= 1
        if len(barriers) == w and outstanding[w] == 0:
            barriers.append(now)
        if len(barriers) > w and barriers[w] + gaps[w] == now:
            opening.append(now)
            w += 1
            continue
        for lane, j in enumerate(lanes):
            if j is None and pending:
                head = pending[0]
                if head.horizon <= w and (not head.cpu or head.old_pin < w):
                    j = lanes[lane] = pending.popleft()
                    history[j.order] = [lane, now, now + j.read]
            if j is not None:
                row = history[j.order]
                if len(row) == 3 and row[2] <= now and j.reserve <= w:
                    row.extend((now, now + j.put))
        upcoming = [history[j.order][-1] for j in lanes if j and history[j.order][-1] > now]
        if len(barriers) > w:
            upcoming.append(barriers[w] + gaps[w])
        need(upcoming and min(upcoming) > now, "no valid service/graph transition")
        now = min(upcoming)
    need(not pending and all(j is None for j in lanes), "call drain")
    return opening, barriers, [[k, *v] for k, v in sorted(history.items())]


def audit(jobs, entry, gaps, witness):
    opening, joined, events = witness
    need(
        opening[0] == entry
        and len(joined) == len(gaps) == len(opening) - 1
        and all(
            a <= b and b + gap == c
            for a, b, gap, c in zip(opening[:-1], joined, gaps, opening[1:], strict=True)
        ),
        "wave barriers",
    )
    by_id = {j.order: j for j in jobs}
    need(len(events) == len(by_id) and {r[0] for r in events} == by_id.keys(), "generation set")
    lanes, slots = defaultdict(list), defaultdict(list)
    counts = Counter()
    for i, lane, begin, ready, put, end in events:
        j = by_id[i]
        need(
            0 <= lane < 4
            and opening[j.horizon] <= begin <= ready <= put <= end <= joined[j.due]
            and put >= opening[j.reserve]
            and ready - begin == j.read
            and end - put == j.put,
            "release, publication or first consumer",
        )
        if j.cpu:
            need(j.old_pin < 0 or begin >= opening[j.old_pin + 1], "victim still pinned")
            slots[j.key[:2]].append((j.key[2], begin, end))
            counts["cpu_read_before_reserve"] += int(begin < opening[j.reserve])
        lanes[lane].append((begin, end))
        counts["parked_worker_ns"] += put - ready
    for intervals in lanes.values():
        need(all(a[1] <= b[0] for a, b in itertools.pairwise(sorted(intervals))), "worker overlap")
    for chain in slots.values():
        need(all(a[2] <= b[1] for a, b in itertools.pairwise(sorted(chain))), "overwritten slot")
    return counts


def add_time(clock, n, duration):
    if n <= 46:
        clock["first_final"] += duration
    if n >= 3:
        clock["decode"] += duration


def decision(floor, witness):
    if any(floor[k] > cap for k, cap in limits.items()):
        return "NO_GO"
    if any(witness[k] > cap for k, cap in limits.items()):
        return "INCONCLUSIVE_SCHEDULE"
    return "GO_TEMPORAL_FIXTURE_ONLY"


def study(rows, screen, primary, old, bound, auth, out, label):
    src = screen["SOURCE"]
    calls, regions, counts = ledger(rows, src, primary)
    waves, _ = src["timeline"](rows)
    host = src["NATIVE"]["host_trace"](rows)
    coarse = L["region_jobs"](rows, src, run_path(screen["HERE"] / "renewal/deadlines.py"))
    spans = defaultdict(list)
    for w in waves:
        spans[w.site[0]].append(w)
    exterior = auth["outside_calls_ns"]
    parent_rows, parent_clock = [], exterior.copy()
    controls, models, certificates = Counter(), {}, {}
    clocks = {name: exterior.copy() for name in ("free_graph", "paid_graph")}
    witnesses = {name: [] for name in clocks}
    occupancy = {name: Counter() for name in clocks}
    last_kind = {}
    for c in host["calls"]:
        n = c["number"]
        ws, jobs = spans[n], calls[n]
        events, violations = coarse_audit(coarse[n], jobs, regions[n])
        parent_rows.append(events)
        add_time(parent_clock, n, events[0][-1])
        controls.update(violations)
        entry = ws[0].start - c["enter_ns"]
        gaps = [
            b - w.end for w, b in zip(ws, [v.start for v in ws[1:]] + [c["return_ns"]], strict=True)
        ]
        need(min([entry, *gaps]) >= 0 and len(gaps) == len(regions[n]), "wave chronology")
        last_kind[n] = entry + sum(gaps)
        models[n] = entry, gaps, interval_edges(jobs, len(gaps))
        for name in clocks:
            first, costs = (entry, gaps) if name == "paid_graph" else (0, [0] * len(gaps))
            path = schedule(jobs, first, costs)
            occupancy[name].update(audit(jobs, first, costs, path))
            add_time(clocks[name], n, path[0][-1])
            witnesses[name].append(path)

    parent_digest = run_path(HERE / "composition.py")["digest"](parent_rows)
    need(
        parent_digest == old["schedule_sha256"]
        and parent_clock == old["near_free_cpu_set_schedule_ns"],
        "original four-worker schedule or clocks",
    )
    for phase, data in bound["phases"].items():
        need(
            sum(v for n, v in last_kind.items() if screen["phase"](n) == phase)
            == data["entry_ns"] + data["cpu_gaps_ns"] + data["cuda_gaps_ns"],
            "graph prices",
        )
    for name, paths in witnesses.items():
        file = out / (label + "-" + name + ".json.gz")
        data = json.dumps(paths, separators=(",", ":")).encode() + b"\n"
        with file.open("xb") as f:
            f.write(gzip.compress(data, compresslevel=6, mtime=0))
        certificates[name] = sha(file)

    def floor(pct):
        clock = exterior.copy()
        for n, (entry, gaps, edges) in models.items():
            add_time(clock, n, graph_floor(entry, gaps, edges, pct))
        return clock

    results = {}
    for name, pct in (("free_graph", 0), ("paid_graph", 100)):
        low = floor(pct)
        need(all(low[k] <= c for k, c in clocks[name].items()), "floor exceeds verified schedule")
        results[name] = dict(
            floor_ns=low,
            schedule_ns=clocks[name],
            decision=decision(low, clocks[name]),
            schedule_sha256=certificates[name],
            occupancy=dict(occupancy[name]),
        )
    cut = None
    if all(v <= limits[k] for k, v in results["free_graph"]["floor_ns"].items()) and any(
        v > limits[k] for k, v in results["paid_graph"]["floor_ns"].items()
    ):
        lo, hi = 0, 100
        while hi - lo > 1:
            pct = (hi + lo) // 2
            if all(v <= limits[k] for k, v in floor(pct).items()):
                lo = pct
            else:
                hi = pct
        cut = dict(
            max_graph_percent=lo, fits_ns=floor(lo), first_failing_percent=hi, fails_ns=floor(hi)
        )
    return dict(
        population=dict(counts),
        original_schedule_sha256=parent_digest,
        coarse_schedule_violations=dict(controls),
        regimes=results,
        graph_cut=cut,
        exterior_ns=exterior,
        journal_sha256=auth["journal_sha256"],
        trajectory_sha256=auth["trajectory_sha256"],
    )


def run(archive, out):
    need(
        sha(HERE / "slot-lifetime.md") == METHOD and sha(HERE / "composition.json") == PARENT,
        "protocol or original combination",
    )
    screen = run_path(HERE.parents[1] / "screen.py")
    src = screen["SOURCE"]
    primary = run_path(screen["HERE"] / "primary/replay.py")
    previous = src["pinned"](HERE / "composition.json", PARENT)
    bound = src["pinned"](HERE / "bound.json", L["PARENT"])
    baseline = src["pinned"](
        screen["NATURAL"] / "prefill_retention/request_cost/receipt.json", screen["PRIOR"]
    )
    arms = {}
    for label in ("P97", "P106"):
        _, auth = screen["read_arm"](archive, label, baseline[label])
        name, seal, _ = src["SOURCES"][label]
        folder = archive / ("part-" + label[1:]) / name
        if label == "P97":
            rows, _ = src["T"]["PFJ"]["read_journal"](folder / "ON/raw/events.pfj")
        else:
            _, rows, _, _ = src["Q"]["read_new"](folder, seal)
        need(auth["journal_sha256"] == bound["traces"][label]["journal_sha256"], "journal seal")
        arms[label] = study(
            rows,
            screen,
            primary,
            previous["traces"][label],
            bound["traces"][label],
            auth,
            out,
            label,
        )
    need(
        arms["P97"]["population"] == arms["P106"]["population"]
        and arms["P97"]["trajectory_sha256"] == arms["P106"]["trajectory_sha256"],
        "two different trajectories or binding populations",
    )
    return dict(
        classification="SIMULATED_ORACLE",
        protocol_sha256=METHOD,
        source_sha256=sha(Path(__file__)),
        parent_sha256=PARENT,
        limits_ns=limits,
        traces=arms,
        model_forwards=0,
        gpu_forwards=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    args = p.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    try:

        def git(*args):
            return subprocess.check_output(["git", *args], cwd=HERE, text=True).strip()

        need(not git("status", "--porcelain"), "unclean measurement tree")
        provenance = dict(
            commit=git("rev-parse", "HEAD"),
            tree=git("rev-parse", "HEAD^{tree}"),
            protocol_sha256=METHOD,
            program_sha256=sha(Path(__file__)),
        )
        (args.new_output_dir / "provenance.json").write_text(
            json.dumps(provenance, indent=2) + "\n"
        )
        result = run(args.archive, args.new_output_dir)
    except Exception as exc:
        missing = (
            isinstance(exc, FileNotFoundError)
            and exc.filename
            and Path(exc.filename).resolve().is_relative_to(args.archive.resolve())
        )
        result = dict(
            classification="NOT_RUN_RAW_REQUIRED" if missing else "FAIL_PRESERVED", reason=str(exc)
        )
    tmp = args.new_output_dir / ".receipt.tmp"
    with tmp.open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    tmp.rename(args.new_output_dir / "slot-lifetime.json")
    print(result["classification"], result.get("reason", ""))
    raise SystemExit(result["classification"] != "SIMULATED_ORACLE")
