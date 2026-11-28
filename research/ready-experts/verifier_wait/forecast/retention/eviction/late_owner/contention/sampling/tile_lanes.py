"""Test the compulsory four-worker service inside two potentially overlapping prefill tiles."""

import argparse
import hashlib
import heapq
import json
import os
from bisect import bisect_left
from collections import deque
from functools import partial
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
C = run_path(HERE / "tile_cost.py")
S, X, F, V, T, R, need, sha, save = (
    C[k] for k in ("S", "X", "F", "V", "T", "R", "need", "sha", "save")
)
METHOD = "2c07a37d8215ae950c00ef74329713c94a945e8711a253646ba883dfd1f8d377"
PRIOR = "8cfe7485cfcdad0619167516a19fb3b1271c32d370dfe31bfadce7cbdccb74ce"


def digest(values):
    return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()


def stage_dag(stages):
    # Monotone order A1, B1, A2, B2 also orders B(i) -> A(i+2).
    durations = [duration for pair in stages for duration in pair]
    after = [[] for _ in durations]
    earliest = [0] * len(durations)
    for i in range(len(stages)):
        a = 2 * i
        after[a].append(a + 1)
        if i + 1 < len(stages):
            after[a].append(a + 2)
            after[a + 1].append(a + 3)
        if i + 2 < len(stages):
            after[a + 1].append(a + 4)
    for idx, next_nodes in enumerate(after):
        for nxt in next_nodes:
            earliest[nxt] = max(earliest[nxt], earliest[idx] + durations[idx])
    suffix = [0] * len(durations)
    for idx in reversed(range(len(durations))):
        suffix[idx] = max((durations[nxt] + suffix[nxt] for nxt in after[idx]), default=0)
    base = earliest[-1] + durations[-1]
    witness = C["P"]["pipeline"](stages)
    need(
        earliest == [p[col] for p in witness for col in (0, 2)] and base == witness[-1][-1],
        "critical paths of the two-tile DAG",
    )
    return earliest, suffix, durations, base


def jobs_in_stages(tile_jobs, stages, markers, region):
    earliest, suffix, durations, base = stage_dag(stages)
    jobs = []
    for tile, layer, start, end, items in tile_jobs:
        tier = int(layer >= 25)
        stage = 2 * (tile - 1) + tier
        lo, hi = markers[tile - 1][1 + 2 * tier : 3 + 2 * tier]
        need(lo <= start <= end <= hi, "consumer outside stage")
        pre, body, post = region(2, lo, start), region(2, start, end), region(2, end, hi)
        need(
            pre + body + post == durations[stage]
            and max(v for _, v in items) <= body
            and sum(v for _, v in items) <= 4 * body,
            "stage partition or worker work",
        )
        for ordinal, cost in items:
            jobs.append(
                (
                    ordinal,
                    cost,
                    earliest[stage] + pre,
                    suffix[stage] + post,
                    earliest[stage] + pre + body,
                )
            )
    need(len(jobs) == len({j[0] for j in jobs}), "generation in multiple windows")
    return sorted(jobs), base


def max_service(windows):
    # The interval node receives at most one lane per job and offers four lanes to the sink.
    need(bool(windows), "empty flow workload")
    cuts = sorted({v for _, _, a, b in windows for v in (a, b)})
    n = len(windows)
    source, sink = 0, n + len(cuts)
    graph = [[] for _ in range(sink + 1)]

    def edge(u, v, cap):
        front = [v, cap, None]
        back = [u, 0, front]
        front[2] = back
        graph[u].append(front)
        graph[v].append(back)

    for j, (_, d, a, b) in enumerate(windows, 1):
        need(a <= b and d >= 0, "flow window or demand")
        edge(source, j, d)
        for k in range(bisect_left(cuts, a), bisect_left(cuts, b)):
            edge(j, n + 1 + k, cuts[k + 1] - cuts[k])
    for k, (a, b) in enumerate(zip(cuts, cuts[1:], strict=False)):
        edge(n + 1 + k, sink, 4 * (b - a))
    total = sum(d for _, d, _, _ in windows)
    sent = 0
    while True:
        level = [-1] * len(graph)
        level[source] = 0
        queue = deque([source])
        while queue:
            u = queue.popleft()
            for v, available, _ in graph[u]:
                if available and level[v] < 0:
                    level[v] = level[u] + 1
                    queue.append(v)
        if level[sink] < 0:
            break
        cursor = [0] * len(graph)

        def send(u, limit, level=level, cursor=cursor):
            if u == sink:
                return limit
            while cursor[u] < len(graph[u]):
                e = graph[u][cursor[u]]
                if e[1] and level[e[0]] == level[u] + 1:
                    push = send(e[0], min(limit, e[1]))
                    if push:
                        e[1] -= push
                        e[2][1] += push
                        return push
                cursor[u] += 1
            return 0

        while pushed := send(source, total):
            sent += pushed
    # Independent capacity of the resulting min-cut using original demands and true widths.
    reachable = [j for j in range(1, n + 1) if level[j] >= 0]
    bins = {k for k in range(len(cuts) - 1) if level[n + 1 + k] >= 0}
    capacity = sum(d for j, (_, d, _, _) in enumerate(windows, 1) if level[j] < 0)
    for j in reachable:
        _, _, a, b = windows[j - 1]
        capacity += sum(
            cuts[k + 1] - cuts[k]
            for k in range(bisect_left(cuts, a), bisect_left(cuts, b))
            if k not in bins
        )
    capacity += sum(4 * (cuts[k + 1] - cuts[k]) for k in bins)
    need(capacity == sent <= total, "max-flow/min-cut certificate")
    # Release reverse-edge cycles before solving the next deadline.
    for neighbors in graph:
        for e in neighbors:
            e[2] = None
    return dict(
        feasible=sent == total,
        demand_worker_ns=total,
        flow_worker_ns=sent,
        cut_capacity_worker_ns=capacity,
        deficit_worker_ns=total - sent,
        cut_jobs=len(reachable),
        cut_intervals=len(bins),
        atomic_intervals=len(cuts) - 1,
        cut_sha256=digest([[windows[j - 1][0] for j in reachable], sorted(bins)]),
    )


def dispatch(windows):
    # Earliest deadline among available generations. Stay on the same lane to final publication.
    waiting = sorted((a, b, i, d) for i, d, a, b in windows if d)
    occupied = [(0, w) for w in range(4)]
    ready = []
    rows = []
    pos = 0
    now = 0
    while ready or pos < len(waiting):
        at, lane = heapq.heappop(occupied)
        at = max(at, now)
        if not ready and pos < len(waiting):
            at = max(at, waiting[pos][0])
        while pos < len(waiting) and waiting[pos][0] <= at:
            a, b, i, d = waiting[pos]
            heapq.heappush(ready, (b, i, d, a))
            pos += 1
        now = at
        b, i, d, a = heapq.heappop(ready)
        at = max(at, a)
        end = at + d
        rows.append((lane, i, at, end, b))
        heapq.heappush(occupied, (end, lane))
    rows.extend((-1, i, a, a, b) for i, d, a, b in windows if not d)
    by_id = {i: (d, a, b) for i, d, a, b in windows}
    need(len(rows) == len(by_id) == len({v[1] for v in rows}), "scheduler coverage")
    finish = [0] * 4
    for lane, i, a, b, _ in rows:
        price, released, _ = by_id[i]
        need(a >= released and b - a == price, "early release or changed job")
        if lane >= 0:
            need(a >= finish[lane], "lane overlap")
            finish[lane] = b
    late = sorted(
        (deadline, i, end - deadline) for _, i, _, end, deadline in rows if end > deadline
    )
    return dict(
        passed=not late,
        jobs=len(rows),
        late_jobs=len(late),
        first_miss=list(late[0]) if late else None,
        worst_lateness_ns=max((v[-1] for v in late), default=0),
        schedule_sha256=digest(rows),
    )


def deadline(jobs, base, target):
    if target < base:
        return dict(target_ns=target, graph_deficit_ns=base - target, status="GRAPH_INFEASIBLE")
    flexible = [(i, c, a, target - tail) for i, c, a, tail, _ in jobs]
    fixed = [(i, c, -(-a * target // base), b * target // base) for i, c, a, _, b in jobs]
    flow = max_service(flexible)
    witness = dispatch(fixed)
    need(not witness["passed"] or flow["feasible"], "witness contradicts flow")
    return dict(
        target_ns=target,
        graph_deficit_ns=0,
        flow=flow,
        witness=witness,
        status="IMPOSSIBLE_EVEN_PREEMPTIBLE"
        if not flow["feasible"]
        else "FOUR_LANE_WITNESS"
        if witness["passed"]
        else "RELAXATION_ONLY",
    )


def evaluate(*, on_jobs=None, site_floor=None, extra_modes=None):
    need(sha(HERE / "windows-protocol.md") == METHOD, "protocol")
    old = S["M"]["verified"](HERE / "evidence-pipeline-20261128-r01/pipeline.json", PRIOR)
    rates = {s: v[1] for s, v in old["rates_ppm"].items()}
    tx, effect = V["sources"]()
    hits = {i for i, r in enumerate(effect, 1) if r[1] is not None}
    physical = X["ORIGINAL"] / "service.json.gz"
    need(sha(physical) == V["SERVICE"], "peer snapshot")
    reads = F["unpack"](physical)
    e = T["E"]
    meta = R["get"](e / "provenance.json")["artifacts_sha256"]
    for f in ("plan.json", "layout.json", "pipeline.json", "service.json.gz"):
        need(sha(e / f) == meta[f], "stage inputs")
    plan = R["get"](e / "plan.json")["order"]
    layout = R["get"](e / "layout.json")["arms"]
    marks = R["get"](e / "pipeline.json")["arms"]
    arms = {}
    for tag, data in R["unpack"]("service.json.gz")["journals"].items():
        native = reads[tag]["jobs"]
        w, _ = C["exposure"](native, hits)
        modes = {}
        layer_modes = {"copied": None, "direct": None} | (extra_modes or {})
        for mode, free_layers in layer_modes.items():
            batch = []
            row, _ = C["scenarios"](
                data,
                native,
                hits,
                w,
                plan,
                rates,
                mode != "copied",
                marks[tag]["markers"],
                layout[tag],
                tag,
                on_stages=lambda *args, batch=batch: batch.append(jobs_in_stages(*args)),
                site_floor=partial(site_floor, tag, mode) if site_floor is not None else None,
                free_hit_layers=free_layers,
            )
            need(
                (site_floor is not None or row == old["arms"][tag]["trained"]["high"][mode])
                and len(batch) == 1,
                "published prices",
            )
            jobs, base = batch[0]
            need(
                {j[0] for j in jobs} == {i for i, t in enumerate(tx, 1) if t[0] == 2},
                "all 148-token generations",
            )
            price = row["speeds"]["8000000000"]["pipeline"]
            floor = price["phases_ns"]["call148"]
            if site_floor is None:
                need(price["decode_ns"] <= 47 * 10**9 // 6, "other client clock")
            integral = floor + 10**10 - price["first_final_ns"]
            credited = floor + 10**10 - price["credited_first_ns"]
            # Reuse identical deadlines (the two client clocks coincide in P97).
            outcomes = {t: deadline(jobs, base, t) for t in sorted({floor, integral, credited})}
            if on_jobs is not None:
                on_jobs(tag, mode, jobs, floor, integral, credited)
            modes[mode] = dict(
                jobs=len(jobs),
                earliest_ns=base,
                work_windows_sha256=digest(jobs),
                budgets={
                    k: outcomes[t]
                    for k, t in (("floor", floor), ("integral", integral), ("credited", credited))
                },
            )
            if site_floor is not None:
                modes[mode]["speeds"] = row["speeds"]
        arms[tag] = modes
    weak = [a["direct"]["budgets"]["credited"]["status"] for a in arms.values()]
    strict = [a["copied"]["budgets"]["integral"]["status"] for a in arms.values()]
    status = (
        "NO_GO_FOUR_WORKERS"
        if any(v in ("GRAPH_INFEASIBLE", "IMPOSSIBLE_EVEN_PREEMPTIBLE") for v in weak)
        else "GO_BOUNDARY_FIXTURE"
        if all(v == "FOUR_LANE_WITNESS" for v in strict)
        else "INCONCLUSIVE"
    )
    return dict(
        status=status,
        method=METHOD,
        projection=PRIOR,
        arms=arms,
        workers=4,
        forwards=0,
        http_requests=0,
        evidence="FORMAL_CONDITIONAL_ON_TRACE_PRICES",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    out = p.add_mutually_exclusive_group(required=True)
    out.add_argument("--new-output-dir", type=Path)
    out.add_argument("--check", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        r = evaluate()
        if a.check:
            need(r == json.loads(a.check.read_bytes()), "published windows")
        else:
            save(a.new_output_dir / "windows.json", r)
        print(r["status"])
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise
