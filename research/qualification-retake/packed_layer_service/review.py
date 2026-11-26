"""Check the actual read/SET journal against five cold C291 generations."""

from collections import defaultdict

ORDER = (45, 60, 98, 57, 49)
SLAB, WINDOW = 4_406_400, 13_221_888


def need(ok, message):
    if not ok:
        raise ValueError(message)


def union(intervals):
    total = 0
    last = 0
    for start, end in sorted(intervals):
        total += max(0, end - max(start, last))
        last = max(last, end)
    return total


def check_prefault(r):
    faults = r.get("prefault_faults")
    need(isinstance(faults, dict) and faults.get("scope") == "RUSAGE_SELF", "prefault scope")
    for counter in ("minflt", "majflt"):
        before, after, delta = (faults.get(f"{counter}_{k}") for k in ("before", "after", "delta"))
        need(all(type(n) is int and n >= 0 for n in (before, after, delta)), "prefault counters")
        need(after - before == delta, "prefault counter delta")


def review_arm(r):
    check_prefault(r)
    need(
        r["schema"] == "tesy-c291-five-misses-v1"
        and r["status"] == "PASS_C291_FIVE_MISS_SERVICE"
        and r["clock"] == "MONOTONIC_RAW_NS",
        "scope",
    )
    layout, mode = r["layout"], r["observer"]
    need(layout in ("DENSE", "STAGED", "DIRECT") and mode in ("MIN", "DETAIL"), "arm")
    sets = 0 if layout == "DIRECT" else 3
    need(
        r["ready_workers"] == r["joined_workers"] == r["workers_before_destructor"] == 4,
        "worker lifecycle",
    )
    need(
        r["load_count"] == 5
        and r["requested_bytes"] == 5 * WINDOW
        and r["logical_bytes"] == 15 * SLAB
        and r["set_count"] == 5 * sets,
        "conservation",
    )
    need(
        r["verified_payload"] is True
        and r["queue_empty"] is True
        and r["confirmed_slots"] == [[e, i, 1] for i, e in enumerate(ORDER)],
        "final geometry",
    )
    start, t0, last, resume, end = (
        r[k] for k in ("outer_start", "t0", "last_publication", "resume", "outer_end")
    )
    need(
        all(type(s) is int for s in (start, t0, last, resume, end))
        and 0 < start <= t0 < last <= resume <= end,
        "endpoints",
    )
    result = {
        "publication_ns": last - t0,
        "resume_ns": resume - t0,
        "wake_after_publication_ns": resume - last,
        "outer_ns": end - start,
        "pre_release_ns": t0 - start,
    }
    events = r["events"]
    if mode == "MIN":
        need(events == [], "MIN contains detailed clocks")
        return result
    need(len(events) == 5 * (4 + 2 * sets), "event coverage")
    jobs = defaultdict(dict)
    for row in events:
        kind = row["event"]
        e = row["expert"]
        w = row["worker"]
        k = row["component"]
        n = row["bytes"]
        t = row["ns"]
        need(
            e in ORDER and row["generation"] == 1 and row["slot"] == ORDER.index(e),
            "event identity",
        )
        need(type(t) is int and start <= t <= last and type(w) is int, "event clock or worker type")
        need((w == -1 if kind == "enqueue" else 0 <= w < 4), "event actor")
        if kind in ("read_begin", "read_end"):
            need(k == -1 and n == WINDOW, "READ bounds")
        elif kind in ("set_begin", "set_end"):
            need(0 <= k < sets and n == SLAB, "SET bounds")
        else:
            need(kind in ("enqueue", "publish") and k == -1 and n == 0, "unknown event or payload")
        key = kind, k
        need(key not in jobs[e], "duplicate event")
        jobs[e][key] = (t, w)
    queues = []
    publishes = []
    reads = []
    copies = []
    workers = defaultdict(list)
    per_job = []
    for e in ORDER:
        job = jobs[e]

        def step(kind, component=-1, job=job):
            need((kind, component) in job, "missing event")
            return job[kind, component]

        q, _ = step("enqueue")
        p, w = step("publish")
        rb, rbw = step("read_begin")
        re, rew = step("read_end")
        need(start <= q <= t0 <= rb <= re <= p <= last and rbw == rew == w, "READ order/actor")
        cursor = re
        copy_ns = 0
        for k in range(sets):
            lo, wa = step("set_begin", k)
            hi, wb = step("set_end", k)
            need(wa == wb == w and cursor <= lo <= hi <= p, "SET order/actor")
            copies.append((lo, hi))
            copy_ns += hi - lo
            cursor = hi
        queues.append(q)
        publishes.append(p)
        reads.append((rb, re))
        workers[w].append((rb, p))
        per_job.append(
            dict(
                expert=e,
                slot=ORDER.index(e),
                worker=w,
                read_ns=re - rb,
                set_worker_ns=copy_ns,
                publish_offset_ns=p - t0,
                after_read_set_ns=p - cursor,
            )
        )
    need(queues == sorted(queues) and max(publishes) == last, "last publication or FIFO")
    for spans in workers.values():
        spans.sort()
        need(
            all(a[1] <= b[0] for a, b in zip(spans, spans[1:], strict=False)),
            "worker handles consecutive jobs before publication",
        )
    result.update(
        read_worker_ns=sum(b - a for a, b in reads),
        set_worker_ns=sum(b - a for a, b in copies),
        read_union_ns=union(reads),
        set_union_ns=union(copies),
        read_or_set_union_ns=union(reads + copies),
        last_experts=[e for e, p in zip(ORDER, publishes, strict=True) if p == last],
        jobs=per_job,
    )
    return result
