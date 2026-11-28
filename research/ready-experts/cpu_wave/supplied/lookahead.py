"""Bound and schedule one-region oracle READs with four owned buffers and target-gated SETs."""

import argparse
import itertools
import json
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
BOUND = run_path(HERE / "executor_bound.py")
need, sha, LIMITS, PHASES = (BOUND[k] for k in ("need", "sha", "LIMITS", "PHASES"))
METHOD = "8825978835384a31f17f35d24508ca41ecf94c187bfee864ddeb657f6eaad015"
PARENT = "469974713c73c552e0c7a6f051565ebce8043cb63e789e31be9be636e06c1636"
PAYLOAD = 13_219_200


@dataclass(frozen=True)
class Job:
    order: int
    group: int
    read: int
    put: int


def floor(groups, lead):
    # t[d] is the earliest possible completion of regions [0,d). Units are quarter-ns.
    totals = [sum(j.read + j.put for j in g) for g in groups]
    longest = [max((j.read + j.put for j in g), default=0) for g in groups]
    puts = [sum(j.put for j in g) for g in groups]
    long_put = [max((j.put for j in g), default=0) for g in groups]
    t = [0] * (len(groups) + 1)
    for s in range(len(groups)):
        work = single = 0
        for g in range(s, len(groups)):
            all_inside = max(0, g - lead) >= s
            work += totals[g] if all_inside else puts[g]
            single = max(single, longest[g] if all_inside else long_put[g])
            t[g + 1] = max(t[g + 1], t[s] + max(work, 4 * single))
    return (t[-1] + 3) // 4


def audit(groups, lead, opening, events):
    jobs = {j.order: j for group in groups for j in group}
    need(
        jobs.keys() == events.keys()
        and opening[0] == 0
        and len(opening) == len(groups) + 1
        and all(a <= b for a, b in itertools.pairwise(opening)),
        "all jobs and boundaries",
    )
    lanes = defaultdict(list)
    early, parked = [], []
    worker_wait = 0
    for i, (lane, begin, ready, put, end) in events.items():
        job = jobs[i]
        need(
            0 <= lane < 4
            and opening[max(0, job.group - lead)] <= begin <= ready <= put <= end
            and opening[job.group] <= put
            and end <= opening[job.group + 1]
            and ready - begin == job.read
            and end - put == job.put,
            "release, dependency or service",
        )
        lanes[lane].append((begin, end))
        worker_wait += put - ready
        if begin < opening[job.group]:
            early.extend(((begin, 1), (opening[job.group], -1)))
        if ready < opening[job.group]:
            parked.extend(((ready, 1), (opening[job.group], -1)))
    for lane in lanes.values():
        need(
            all(a[1] <= b[0] for a, b in itertools.pairwise(sorted(lane))), "worker/buffer overlap"
        )

    def peak(spans):
        # Ends sort before starts at equal times.
        n = high = 0
        for _, v in sorted(spans):
            n += v
            high = max(n, high)
        need(n == 0 and high <= 4, "buffer conservation")
        return high

    return dict(
        early_reads=len(early) // 2,
        ready_before_route=len(parked) // 2,
        early_buffer_peak=peak(early),
        parked_buffer_peak=peak(parked),
        worker_parked_ns=worker_wait,
        generations=len(jobs),
    )


def schedule(groups, lead):
    queues = [deque(g) for g in groups]
    remaining = list(map(len, groups))
    workers = [None] * 4
    events, opening = {}, [0]
    now = g = 0
    while g < len(groups):
        for lane, item in enumerate(workers):
            if item is None:
                continue
            job, stage, due = item
            if due == now and stage == "SET":
                remaining[job.group] -= 1
                events[job.order].append(now)
                workers[lane] = None
            elif due == now and stage == "READ":
                events[job.order].append(now)
                workers[lane] = (job, "HELD", None)
        while g < len(groups) and remaining[g] == 0:
            g += 1
            opening.append(now)
        if g == len(groups):
            break
        for lane, item in enumerate(workers):
            if item is not None:
                job, stage, _ = item
                if stage == "HELD" and job.group == g:
                    events[job.order].append(now)
                    workers[lane] = (job, "SET", now + job.put)
                continue
            dest = g if queues[g] else g + 1
            if dest >= len(groups) or dest > g + lead or not queues[dest]:
                continue
            job = queues[dest].popleft()
            need(job.order not in events and job.read > 0 and job.put > 0, "unique positive job")
            events[job.order] = [lane, now]
            workers[lane] = (job, "READ", now + job.read)
        deadlines = [item[2] for item in workers if item and item[2] is not None]
        need(deadlines and min(deadlines) > now, "no service progress")
        now = min(deadlines)
    need(all(item is None for item in workers), "undrained final buffer")
    info = audit(groups, lead, opening, events)
    return now, info, [opening, [[k, *v] for k, v in sorted(events.items())]]


def region_jobs(rows, src, dead):
    waves, sites = src["timeline"](rows)
    sequence = [key for key, _ in itertools.groupby(waves, lambda x: x.site[:3])]
    need(len(set(sequence)) == len(sequence), "noncontiguous region")
    reserves, published, read, sets = {}, {}, {}, defaultdict(list)
    for e in rows:
        k = src["key"](e)
        if e.kind == 11:
            reserves[k] = e.ns
        elif e.kind == 17:
            published[k] = e.ns
        elif e.kind == 30:
            read[k] = e.ns - e.begin
        elif e.kind == 16:
            sets[k].append(e.ns - e.begin)
    tags = dead["consumers"](waves, {k: (v, published[k]) for k, v in reserves.items()})
    need(
        Counter(tags.values()) == {"same_wave": 1918, "later_wave_same_tile_layer": 436}
        and reserves.keys() == read.keys() == sets.keys() == sites.keys(),
        "mandatory service population",
    )
    by_site = defaultdict(list)
    for seq, key in enumerate(reserves):
        need(len(sets[key]) == 3, "all three SET components")
        by_site[sites[key][:3]].append((seq, read[key], sum(sets[key])))
    calls = {}
    for num, members in itertools.groupby(sequence, lambda key: key[0]):
        calls[num] = [[Job(i, g, r, s) for i, r, s in by_site[k]] for g, k in enumerate(members)]
    need(list(calls) == list(range(1, 49)), "external call order")
    return calls


def study(repo, archive, parent, out):
    need(sha(HERE / "lookahead.md") == METHOD and sha(parent) == PARENT, "campaign or parent seal")
    old = json.loads(parent.read_bytes())
    base = repo / "research/ready-experts"
    screen = run_path(base / "screen.py")
    src = screen["SOURCE"]
    dead = run_path(base / "renewal/deadlines.py")
    prior = src["pinned"](
        screen["NATURAL"] / "prefill_retention/request_cost/receipt.json", screen["PRIOR"]
    )
    trials, decisions = {}, {}
    for label in ("P97", "P106"):
        _, auth = screen["read_arm"](archive, label, prior[label])
        compare = old["traces"][label]
        need(auth["journal_sha256"] == compare["journal_sha256"], "parent journal")
        name, h, _ = src["SOURCES"][label]
        root = archive / ("part-" + label[1:]) / name
        if label == "P97":
            rows, _ = src["T"]["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
        else:
            _, rows, _, _ = src["Q"]["read_new"](root, h)
        calls = region_jobs(rows, src, dead)
        trials[label] = {}
        for lead in (0, 1):
            phases = defaultdict(Counter)
            peak = held_peak = 0
            witness = []
            for num, groups in calls.items():
                lower = floor(groups, lead)
                end, info, events = schedule(groups, lead)
                need(lower <= end, "lower bound exceeds temporal witness")
                peak = max(peak, info.pop("early_buffer_peak"))
                held_peak = max(held_peak, info.pop("parked_buffer_peak"))
                phases[screen["phase"](num)].update(info | dict(lower_ns=lower, schedule_ns=end))
                witness.append(events)
            clocks = {}
            for metric, relevant in PHASES.items():
                ext = compare["outside_ns"][metric]
                lower = sum(phases[p]["lower_ns"] for p in relevant)
                sched = sum(phases[p]["schedule_ns"] for p in relevant)
                if lead == 0:
                    need(
                        lower
                        == compare["four_worker_service_floors"]["service_layer_release_ns"][
                            metric
                        ]["native_ns"]
                        and peak == held_peak == 0,
                        "zero-lookahead control",
                    )
                clocks[metric] = dict(
                    lower_free_exterior_ns=lower,
                    schedule_free_exterior_ns=sched,
                    lower_full_client_ns=ext + lower,
                    schedule_full_client_ns=ext + sched,
                    full_client_witness_margin_ns=LIMITS[metric] - ext - sched,
                )
            path = out / f"{label}-{lead}.json"
            with path.open("x") as f:
                json.dump(witness, f, separators=(",", ":"))
                f.write("\n")
            trials[label][str(lead)] = dict(
                phases=phases,
                clocks=clocks,
                early_buffer_peak=peak,
                parked_buffer_peak=held_peak,
                witness_sha256=sha(path),
                early_logical_bytes=sum(p["early_reads"] for p in phases.values()) * PAYLOAD,
            )
        clocks = trials[label]["1"]["clocks"]
        fails = [k for k, d in clocks.items() if d["lower_full_client_ns"] > LIMITS[k]]
        fits = all(d["full_client_witness_margin_ns"] >= 0 for d in clocks.values())
        decisions[label] = (
            "NO_GO_ORACLE_ONE_REGION"
            if fails
            else "GO_TEMPORAL_FIXTURE_ONLY"
            if fits
            else "INCONCLUSIVE_SCHEDULE"
        )
    all_results = list(decisions.values())
    return dict(
        classification="SIMULATED_ORACLE",
        protocol_sha256=METHOD,
        source_sha256=sha(Path(__file__)),
        parent_sha256=PARENT,
        traces=trials,
        decisions=decisions,
        new_model_loads=0,
        decision="NO_GO_ORACLE_ONE_REGION"
        if "NO_GO_ORACLE_ONE_REGION" in all_results
        else "GO_TEMPORAL_FIXTURE_ONLY"
        if len(set(all_results)) == 1 and all_results[0].startswith("GO")
        else "INCONCLUSIVE_SCHEDULE",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=HERE.parents[3])
    for k in ("archive", "parent", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        r = study(a.repo, a.archive, a.parent, a.new_output_dir)
    except Exception as exc:
        missing = isinstance(exc, FileNotFoundError) and Path(
            exc.filename
        ).resolve().is_relative_to(a.archive.resolve())
        r = dict(
            classification="NOT_RUN_RAW_REQUIRED" if missing else "FAIL_PRESERVED", reason=str(exc)
        )
    with (a.new_output_dir / "lookahead.json").open("x") as f:
        json.dump(r, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(r["classification"], r.get("decision", r.get("reason", "")))
    raise SystemExit(r["classification"] != "SIMULATED_ORACLE")
