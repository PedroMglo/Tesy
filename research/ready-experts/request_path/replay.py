"""Reprice native event dependencies. All time values are integer nanoseconds."""

from collections import Counter
from dataclasses import dataclass


def require(ok, message):
    if not ok:
        raise ValueError(message)


PHASES = ("prefill_5", "prefill_148", "decode_to_first", "decode_tail")
FIRST = 10_000_000_000
DECODE = 47_000_000_000 // 6
PPM = 1_000_000


def phase(call):
    return PHASES[0 if call == 1 else 1 if call == 2 else 2 if call <= 46 else 3]


def clocks(source, savings):
    p, q, d, z = (savings[k] for k in PHASES)
    raw = source["client"]
    out = dict(
        first=raw["first"] - p - q - d,
        valid=raw["valid"] - p - q - d - z,
        prefill=raw["prefill"] - p - q,
        decode=raw["decode"] - d - z,
    )
    require(min(out.values()) > 0 and out["valid"] >= out["first"], "clock outside scope")
    return out | dict(
        first_margin=FIRST - out["first"],
        decode_margin=DECODE - out["decode"],
        phase_saved=dict(savings),
    )


@dataclass
class Node:
    stamp: int
    dependencies: tuple
    gates: tuple
    residual: int
    component: str
    job: int


def build(source, native, queue, reverse_ties=False):
    jobs = native["jobs"]
    events = []
    for i, (enter, stop) in enumerate(source["calls"]):
        events.extend(((enter, "enter", i), (stop, "return", i)))
    for i, (_, start, enter, leave, end, _, _) in enumerate(source["waves"]):
        events.extend(
            ((start, "remap", i), (enter, "wait", i), (leave, "wake", i), (end, "end", i))
        )
    for i, job in enumerate(jobs):
        events.extend(
            (
                (job[2], "reserve", i),
                (queue["useful"][i], "enqueue", i),
                (job[4], "claim", i),
                (job[-1], "publish", i),
            )
        )
        for start, kind in ((5, "read"), (7, "set"), (9, "set"), (11, "set")):
            events.extend(((job[start], "begin", i), (job[start + 1], kind, i)))
    for i, (_, kind, _, enqueue, pop) in enumerate(queue["skipped"]):
        require(kind == 14, "unknown cancellation")
        events.extend(((enqueue, "duplicate", i), (pop, "skip", i)))
    events.sort()
    ties = 0
    for pos in range(1, len(events)):
        before, after = events[pos - 1], events[pos]
        if before[0] != after[0]:
            continue
        # A service start mutates only its own lane. A simultaneous start
        # or claim on another lane does not read that node.
        require(
            before[1] == "begin"
            and after[1] in ("begin", "claim")
            and jobs[before[2]][3] != jobs[after[2]][3]
            and (pos + 1 == len(events) or events[pos + 1][0] > after[0]),
            "unidentified simultaneous dependencies",
        )
        ties += 1
        if reverse_ties:
            events[pos - 1], events[pos] = after, before
    base = events[0][0]
    require(events[0][1:] == ("enter", 0), "unclean entry")
    nodes = [Node(base, (), (), 0, "", -1)]
    stamps = [base]
    host = mutex = last_pop = 0
    lanes = [0] * 4
    slots, publications, enqueues, duplicates, claims = {}, {}, {}, {}, {}
    mutex_events = {
        "remap",
        "reserve",
        "enqueue",
        "duplicate",
        "wait",
        "wake",
        "end",
        "claim",
        "skip",
        "publish",
    }
    host_events = {
        "enter",
        "return",
        "remap",
        "reserve",
        "enqueue",
        "duplicate",
        "wait",
        "wake",
        "end",
    }
    boundaries, stats = {}, Counter()
    stats["independent_timestamp_pairs"] = ties
    for stamp, kind, i in events:
        index = len(nodes)
        dependencies, gates = [], []
        job_id = -1
        if kind in host_events:
            dependencies.append(host)
            host = index
            if kind in ("enter", "return"):
                boundaries[kind, i] = index
            elif kind == "reserve":
                layer, slot, generation, _ = jobs[i][0]
                old = slots.get((layer, slot))
                if old is not None:
                    require(jobs[old][0][2] + 1 == generation, "stale victim")
                    gates.append(publications[old])
                    stats["previous_publication_edges"] += 1
                slots[layer, slot] = i
            elif kind == "enqueue":
                enqueues[i] = index
            elif kind == "duplicate":
                target = queue["skipped"][i][0]
                require(target not in publications and target in enqueues, "non-loading duplicate")
                duplicates[i] = index
            elif kind == "wake":
                required = source["waves"][i][5]
                dependencies.extend(publications[j] for j in required)
                stats["demand_producer_edges"] += len(required)
        elif kind in ("claim", "skip"):
            if kind == "claim":
                worker, entry = jobs[i][3], enqueues[i]
                claims[i] = index
            else:
                target, _, worker, _, _ = queue["skipped"][i]
                entry = duplicates[i]
                gates.append(claims[target])
            dependencies.extend((entry, lanes[worker], last_pop))
            last_pop = lanes[worker] = index
        else:
            job_id = i
            worker = jobs[i][3]
            dependencies.append(lanes[worker])
            lanes[worker] = index
            if kind == "publish":
                publications[i] = index
        if kind in mutex_events:
            gates.append(mutex)
            mutex = index
        residual = stamp - max(stamps[p] for p in dependencies)
        require(residual >= 0 and all(stamps[g] <= stamp for g in gates), "causal inversion")
        nodes.append(Node(stamp, tuple(dependencies), tuple(gates), residual, kind, job_id))
        stamps.append(stamp)
        stats[kind] += 1
    require(
        len(publications) == len(claims) == len(enqueues) == len(jobs)
        and len(duplicates) == len(queue["skipped"]),
        "undrained work",
    )
    last = stamps[boundaries["return", 47]]
    require(
        max(stamps[n] for n in lanes) <= last <= min(t for t, _ in source["exits"])
        and max(t for t, _ in source["exits"]) <= source["end"],
        "shutdown lineage",
    )
    require(
        stats["reserve"] == stats["claim"] == stats["publish"] == stats["read"] == 2354
        and stats["set"] == 7062
        and stats["wake"] == 2987,
        "population",
    )
    return nodes, boundaries, dict(stats)


def simulate(source, nodes, boundaries, free_read, free_set, control=False):
    times = [nodes[0].stamp]
    for node in nodes[1:]:
        residual = node.residual
        if (node.component == "read" and node.job in free_read) or (
            node.component == "set" and node.job in free_set
        ):
            residual = 0
        ready = max(times[p] for p in node.dependencies) + residual
        value = max(ready, max((times[p] for p in node.gates), default=0))
        require(value <= node.stamp and (not control or value == node.stamp), "event replay")
        times.append(value)
    savings = Counter(dict.fromkeys(PHASES, 0))
    for i, (start, end) in enumerate(source["calls"]):
        first, last = (times[boundaries[k, i]] for k in ("enter", "return"))
        if i:
            require(
                first - times[boundaries["return", i - 1]] == start - source["calls"][i - 1][1],
                "inter-call time changed",
            )
        savings[phase(i + 1)] += (end - start) - (last - first)
    return clocks(source, savings)


def compulsory(source, jobs, hits):
    terms, seen, counts = [], set(), Counter()
    for site, start, enter, wake, end, demanded, initial in source["waves"]:
        work = []
        require(start <= enter <= wake <= end, "service window")
        counts["initial_demand_edges"] += initial
        for i in demanded:
            j = jobs[i]
            if j[1] != site:
                continue
            require(i not in seen and start <= j[2] <= j[4] <= j[-1] <= wake, "compulsory interval")
            seen.add(i)
            read = j[6] - j[5]
            sets = sum(j[p + 1] - j[p] for p in (7, 9, 11))
            require(0 <= read + sets <= j[-1] - j[4], "component price")
            work.append((i, read, sets))
            counts["cpu" if j[0][0] < 25 else "cuda"] += 1
            counts["hit"] += int(i in hits)
        terms.append((phase(site[0]), site[2] < 25, end - start, enter - start, end - wake, work))
    return terms, dict(counts)


def lower(source, terms, free_read, free_set, cpu_ppm=PPM, cuda_ppm=PPM):
    savings = Counter(dict.fromkeys(PHASES, 0))
    for part, cpu, span, preparation, finish, work in terms:
        costs = [
            (read if i not in free_read else 0) + (sets if i not in free_set else 0)
            for i, read, sets in work
        ]
        price = cpu_ppm if cpu else cuda_ppm
        quarters = max(4 * max(costs, default=0), sum(costs))
        elapsed = (quarters * price + 4 * PPM - 1) // (4 * PPM)
        floor = finish + max(preparation, elapsed)
        require(floor <= span, "four-lane floor exceeds measured remap")
        savings[part] += span - floor
    return clocks(source, savings)


def passes(result):
    return min(result["first_margin"], result["decode_margin"]) >= 0


def ceiling(measure):
    if not passes(measure(0)):
        return None
    if passes(measure(PPM)):
        return PPM
    lo, hi = 0, PPM
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if passes(measure(mid)):
            lo = mid
        else:
            hi = mid
    require(passes(measure(lo)) and not passes(measure(hi)), "price frontier")
    return lo


def grade(source, native, queue, hits):
    jobs = native["jobs"]
    nodes, bounds, conservation = build(source, native, queue)
    reverse, reverse_bounds, reverse_counts = build(source, native, queue, reverse_ties=True)
    require(conservation == reverse_counts, "tied event populations")
    terms, mandatory = compulsory(source, jobs, hits)
    cpu = {i for i, j in enumerate(jobs) if j[0][0] < 25}
    all_jobs = set(range(len(jobs)))
    require(hits <= cpu and len(hits) == 484, "bank tier")
    cases = {
        "DISK": (set(), set()),
        "COPY": (hits, set()),
        "ID": (hits, hits),
        "CPU_FREE": (cpu, cpu),
        "CUDA_FREE": (all_jobs - cpu, all_jobs - cpu),
        "ALL_FREE": (all_jobs, all_jobs),
    }
    fixed, relaxed = {}, {}
    for name, (reads, sets) in cases.items():
        fixed[name] = simulate(source, nodes, bounds, reads, sets, control=name == "DISK")
        require(
            fixed[name]
            == simulate(source, reverse, reverse_bounds, reads, sets, control=name == "DISK"),
            "verdict depends on a tie",
        )
        relaxed[name] = lower(source, terms, reads, sets)
        require(
            all(
                relaxed[name][k] <= fixed[name][k] for k in ("first", "decode", "valid", "prefill")
            ),
            "relaxation above projected clock",
        )
    ratios = {}
    for axis in ("both", "cpu", "cuda"):

        def measured(p, axis=axis):
            return lower(
                source, terms, hits, hits, PPM if axis == "cuda" else p, PPM if axis == "cpu" else p
            )

        ratios[axis] = ceiling(measured)
    last_return = source["calls"][-1][-1]
    return dict(
        nodes_reproduced=len(nodes) - 1,
        conservation=conservation,
        compulsory=mandatory,
        windows_without_victim_wait=len(terms),
        client=source["client"],
        fixed_fifo=fixed,
        relaxed=relaxed,
        max_peer_service_ppm_for_joint=ratios,
        shutdown=dict(
            last_return_to_first_exit_ns=min(t for t, _ in source["exits"]) - last_return,
            last_return_to_end_ns=source["end"] - last_return,
            workers=len(source["exits"]),
            cleanup=source["cleanup"],
        ),
    )
