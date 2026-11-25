"""Independent event validation and critical-path contraction for the frozen fixture."""

import hashlib
from collections import Counter

JOBS = ((0, 28, 3, 1), (0, 24, 14, 1), (0, 8, 6, 1), (0, 16, 35, 1))
ROLES = ("gate", "down", "up")


def need(ok, why):
    if not ok:
        raise ValueError(why)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def union(spans):
    result = last = 0
    for begin, end in sorted(spans):
        result += max(0, end - max(last, begin))
        last = max(last, end)
    return result


def finish(graph, free=False):
    """Nodes are topologically ordered (name, prerequisites, duration, removable)."""
    times = {}
    for name, parents, duration, removable in graph:
        start = max((times[k] for k in parents), default=0)
        times[name] = start + (0 if free and removable else duration)
    return times["return"]


def grade(trace):
    need(
        trace["schema"] == "tesy-pack-events/v1" and trace["clock"] == "VIRTUAL_BARRIER_TICKS",
        "schema",
    )
    rows = trace["records"]
    workers = trace["workers"]
    host = trace["host_tid"]
    need(
        set(workers) == {"0", "1", "2", "3"}
        and len(set(workers.values()) | {host}) == 5
        and all(type(t) is int and t > 0 for t in (*workers.values(), host, trace["pid"]))
        and trace["joined"] == 4
        and trace["saved"] == len(rows)
        and trace["dropped"] == 0,
        "threads/closure",
    )
    need(trace["jobs"] == [list(k) for k in JOBS], "route manifest")
    last = -1
    for n, row in enumerate(rows):
        actor, tick = row["actor"], row["t"]
        need(actor == "host" or (type(actor) is int and 0 <= actor < 4), "actor")
        need(row["tid"] == (host if actor == "host" else workers[str(actor)]), "thread")
        need(row["n"] == n and type(tick) is int and tick >= max(0, last), "common clock")
        last = tick
    keyed = [r for r in rows if "key" in r]
    hosts = [r for r in rows if "key" not in r]
    names = [
        "ENTER",
        "ROUTE",
        "COMPUTE_BEGIN",
        "COMPUTE_END",
        "REMAP_BEGIN",
        "REMAP_END",
        "CONSUME_BEGIN",
        "CONSUME_END",
        "RETURN",
    ]
    need(
        [r["kind"] for r in hosts] == names and all(r["actor"] == "host" for r in hosts),
        "endpoints",
    )
    entry, route, cb, ce, rb, re, use, end, close = hosts
    need(
        entry["t"] == route["t"] == cb["t"] == 0
        and ce["t"] == rb["t"]
        and end["t"] == close["t"]
        and rows[-1] == close
        and rows[0] == entry
        and route["ranks"] == [k[1] for k in JOBS],
        "phase",
    )
    need(set(tuple(r["key"]) for r in keyed) == set(JOBS), "generation identity")
    graph = [("route", [], 0, False), ("compute", ["route"], ce["t"], False)]
    spans = []
    total = Counter()
    expected_output = bytearray()
    publications = []
    published_ticks = []
    for i, key in enumerate(JOBS):
        log = [r for r in keyed if tuple(r["key"]) == key]
        pre = ["RESERVE", "ENQUEUE"] + (["PROMOTE"] if i == 3 else [])
        operations = (
            ["CLAIM", "READ_BEGIN", "READ_END"] + ["SET_BEGIN", "SET_END"] * 3 + ["PUBLISH"]
        )
        events = pre + operations + (["SKIP_DUPLICATE"] if i == 3 else [])
        need([r["kind"] for r in log] == events, "generation lifecycle")
        pre_rows, job = log[: len(pre)], log[len(pre) :]
        need(
            all(r["actor"] == "host" and r["t"] == 0 for r in pre_rows)
            and route["n"] < pre_rows[0]["n"]
            and all(r["actor"] == i for r in job)
            and pre_rows[1]["reason"] == ("preload" if i == 3 else "demand"),
            "queue",
        )
        claim, read_b, read_e = job[:3]
        publish = job[9]
        need(
            claim["t"] == read_b["t"] == 0
            and read_b["offset"] == i * 12
            and read_b["requested"] == read_e["returned"] == 12
            and read_e["errno"] == 0,
            "read extent",
        )
        need(publish["n"] < re["n"] and (i != 3 or job[-1]["n"] < close["n"]), "publish/consume")
        components = [("read", read_b, read_e)]
        for k, role in enumerate(ROLES):
            b, e = job[3 + k * 2 : 5 + k * 2]
            value = bytes([key[0] + k, key[1], key[2], key[3]])
            need(
                b["role"] == e["role"] == role
                and b["bytes"] == e["bytes"] == 4
                and e["sha256"] == sha(value),
                "role/destination/digest",
            )
            expected_output.extend(value)
            components.append(("set", b, e))
        previous = "route"
        previous_tick = claim["t"]
        for n, (kind, b, e) in enumerate(components):
            begin, stop = b["t"], e["t"]
            need(begin == previous_tick and stop > begin, "service boundary")
            name = (i, n)
            graph.append((name, [previous], stop - begin, True))
            total[kind] += stop - begin
            spans.append((begin, stop))
            previous, previous_tick = name, stop
        need(publish["t"] == previous_tick, "publish boundary")
        publications.append(previous)
        published_ticks.append(previous_tick)
    need(sha(expected_output) == use["data_sha256"], "consumer payload")
    need(re["t"] == max(rb["t"], *published_ticks), "READY predicate")
    graph.append(("remap", ["compute", *publications], 0, False))
    visibility = trace["visibility"]
    need(visibility in {"host_synchronous", "unknown"}, "visibility field")
    if visibility == "host_synchronous":
        need(use["t"] == re["t"], "synchronous fence")
    latency = use["t"] - re["t"]
    tail = end["t"] - use["t"]
    need(latency >= 0 and tail > 0, "consumer boundary")
    # For an unresolved gate compare two observationally indistinguishable completions.
    # One independent branch is ready at the observed consumer time. Alternatively,
    # READ/SET visibility trails the last host publication.
    if visibility == "unknown":
        slow_visibility = ("extra", publications, use["t"] - max(published_ticks), True)
        independent = ("extra", ["route"], use["t"], False)
        alternatives = [slow_visibility, independent]
    else:
        alternatives = [("extra", ["route"], 0, False)]
    counterfactuals = []
    for residual in alternatives:
        dag = [*graph, residual, ("return", ["remap", "extra"], tail, False)]
        need(finish(dag) == close["t"], "DAG/observed wall")
        counterfactuals.append(finish(dag, free=True))
    lo, hi = min(counterfactuals), max(counterfactuals)
    return {
        "status": "BOUNDED_UNKNOWN_FENCE"
        if visibility == "unknown"
        else "IDENTIFIED_SYNTHETIC_DAG",
        "clock": trace["clock"],
        "jobs": len(JOBS),
        "claims": len(JOBS),
        "queue_insertions": len(JOBS) + 1,
        "read_worker_ticks": total["read"],
        "set_worker_ticks": total["set"],
        "service_worker_ticks": total.total(),
        "service_union_ticks": union(spans),
        "consumer_ready_blocked_ticks": re["t"] - rb["t"],
        "after_ready_unresolved_ticks": latency,
        "wall_ticks": close["t"],
        "free_delivery_wall_interval_ticks": [lo, hi],
        "exposed_gain_interval_ticks": [close["t"] - hi, close["t"] - lo],
        "consumed_sha256": sha(expected_output),
    }
