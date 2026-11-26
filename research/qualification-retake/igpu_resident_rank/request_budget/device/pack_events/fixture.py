"""Four concurrent workers on one deterministic virtual clock. All data is synthetic."""

import hashlib
import os
import threading

ROLES = ("gate", "down", "up")
JOBS = ((0, 28, 3, 1), (0, 24, 14, 1), (0, 8, 6, 1), (0, 16, 35, 1))
CASES = {"hidden": (10, None), "exposed": (3, None), "unknown-fence": (3, 9)}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def payload(key):
    layer, expert, slot, gen = key
    return b"".join(bytes((layer + role, expert, slot, gen)) for role in range(3))


def capture(compute_ticks, unobserved_until=None):
    if not (type(compute_ticks) is int and 0 <= compute_ticks <= 80):
        raise ValueError("invalid compute duration")
    ready = 7
    host_done = max(ready, compute_ticks)
    consumer = host_done if unobserved_until is None else unobserved_until
    if not (type(consumer) is int and host_done <= consumer <= 100):
        raise ValueError("invalid consumer")
    end = consumer + 2
    barrier = threading.Barrier(5, timeout=5)
    lock = threading.Lock()
    events, tids, workers, errors = [], {}, [], []
    slots = {}

    def record(t, actor, kind, jid=None, **extra):
        with lock:
            row = dict(n=len(events), t=t, actor=actor, tid=threading.get_native_id(), kind=kind)
            if jid is not None:
                row["key"] = list(JOBS[jid])
            events.append(dict(row, **extra))

    def work(jid):
        key = JOBS[jid]
        active = b""
        roles = []
        try:
            with lock:
                tids[str(jid)] = threading.get_native_id()
            for t in range(end + 1):
                barrier.wait()
                if t == 0:
                    if slots[key[2]] != ("loading", key):
                        raise ValueError("claim")
                    record(t, jid, "CLAIM", jid)
                    record(t, jid, "READ_BEGIN", jid, offset=jid * 12, requested=12)
                if t == 4:
                    active = payload(key)
                    record(t, jid, "READ_END", jid, returned=len(active), errno=0)
                if 5 <= t <= 7:
                    i = t - 5
                    roles.append(active[4 * i : 4 * i + 4])
                    record(t, jid, "SET_END", jid, role=ROLES[i], bytes=4, sha256=digest(roles[-1]))
                if 4 <= t <= 6:
                    record(t, jid, "SET_BEGIN", jid, role=ROLES[t - 4], bytes=4)
                if t == ready:
                    with lock:
                        if slots[key[2]] != ("loading", key) or len(roles) != 3:
                            raise ValueError("publish")
                        slots[key[2]] = ("resident", key, b"".join(roles))
                    record(t, jid, "PUBLISH", jid)
                    if jid == 3:
                        record(t, jid, "SKIP_DUPLICATE", jid)
                barrier.wait()
        except Exception as error:
            with lock:
                errors.append(str(error))
            barrier.abort()

    for jid in range(4):
        thread = threading.Thread(target=work, args=(jid,))
        workers.append(thread)
        thread.start()
    try:
        for t in range(end + 1):
            if t == 0:
                record(t, "host", "ENTER")
                record(t, "host", "ROUTE", ranks=[k[1] for k in JOBS])
                record(t, "host", "COMPUTE_BEGIN")
                for jid, key in enumerate(JOBS):
                    slots[key[2]] = ("loading", key)
                    record(t, "host", "RESERVE", jid)
                    record(t, "host", "ENQUEUE", jid, reason="preload" if jid == 3 else "demand")
                record(t, "host", "PROMOTE", 3)
            barrier.wait()
            barrier.wait()
            if t == compute_ticks:
                record(t, "host", "COMPUTE_END")
                record(t, "host", "REMAP_BEGIN")
            if t == host_done:
                if any(state[0] != "resident" for state in slots.values()):
                    raise ValueError("consumer predicate")
                record(t, "host", "REMAP_END")
            if t == consumer:
                data = b"".join(slots[key[2]][2] for key in JOBS)
                if data != b"".join(payload(key) for key in JOBS):
                    raise ValueError("consumer bytes")
                record(t, "host", "CONSUME_BEGIN", data_sha256=digest(data))
            if t == end:
                record(t, "host", "CONSUME_END")
                record(t, "host", "RETURN")
    finally:
        if len(events) == 0 or events[-1]["kind"] != "RETURN":
            barrier.abort()
        for thread in workers:
            thread.join(6)
    if errors or any(thread.is_alive() for thread in workers):
        raise ValueError(f"worker closure {errors}")
    return {
        "schema": "tesy-pack-events/v1",
        "pid": os.getpid(),
        "host_tid": threading.get_native_id(),
        "workers": tids,
        "clock": "VIRTUAL_BARRIER_TICKS",
        "visibility": "unknown" if unobserved_until is not None else "host_synchronous",
        "jobs": [list(key) for key in JOBS],
        "records": events,
        "saved": len(events),
        "dropped": 0,
        "joined": sum(not thread.is_alive() for thread in workers),
    }
