"""Verify the C305 single-layer worker fixture against its independent byte and order contract."""

import gzip
import hashlib
import json
from functools import lru_cache
from itertools import pairwise
from pathlib import Path

SLAB = 4_406_400
DESTINATIONS = ((1, 4, 1), (4, 5, 1), (8, 0, 1), (9, 1, 1))
COUNTERS = dict(
    issued=3,
    reads=3,
    completed_reads=3,
    expired_running=2,
    waits=1,
    consumed=1,
    errors=0,
    peak_running_spec=3,
)
TERMINAL = dict(
    idle=True,
    workers=4,
    queue=0,
    claimed=0,
    shutting_down=False,
    load_failed=False,
    direct_primary=True,
    direct_stage=True,
)
CONTROLLER = (
    "barrier_begin",
    "barrier_end",
    "remap_return",
    "finish_begin",
    "finish_end",
    "shutdown",
)
STAGE = ("stage_start", "stage_complete", "stage_read_begin", "stage_read_end")
DIRECT = ("direct_read_begin", "direct_read_end")
COPY = ("copy_begin", "copy_end")
PRIMARY = ("primary_accept", "primary_publish")
ATTACH = ("park", "resume", "claim")
WORKER = ("worker_enter", "worker_exit")
READ_COPY = (*DIRECT, *COPY, "stage_read_begin", "stage_read_end")
FIELDS = {
    "seq",
    "ns",
    "worker",
    "tid",
    "kind",
    "expert",
    "slot",
    "generation",
    "ticket",
    "component",
}


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def integer(value):
    return type(value) is int


def checks(values, expected):
    need(isinstance(values, dict), "missing summary")
    for key, value in expected.items():
        need(type(values.get(key)) is type(value) and values[key] == value, "wrong " + key)


def digest(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=12)
def reference(expert, component):
    cycle = bytes((expert * 29 + component * 61 + j * 11) % 256 for j in range(251))
    repeats, remainder = divmod(SLAB, len(cycle))
    h = hashlib.sha256()
    h.update(cycle * repeats)
    h.update(cycle[:remainder])
    return h.hexdigest()


def read_slab(path):
    need(path.is_file() and not path.is_symlink(), "missing, linked or nonregular slab")
    h = hashlib.sha256()
    try:
        with gzip.open(path, "rb") as f:
            remaining = SLAB
            while remaining > 0:
                block = f.read(min(remaining, 256 * 1024))
                need(block, "short destination slab")
                h.update(block)
                remaining -= len(block)
            need(not f.read(1), "oversize destination slab")
    except (OSError, EOFError) as exc:
        raise ValueError("corrupt destination gzip") from exc
    return h.hexdigest()


def verify_destinations(rows, arm_dir):
    need(isinstance(rows, list) and len(rows) == len(DESTINATIONS), "four destinations required")
    paths = set()
    verified = []
    for row, (expert, slot, generation) in zip(rows, DESTINATIONS, strict=True):
        keys = dict(expert=expert, slot=slot, generation=generation)
        checks(row, keys)
        names = row.get("files")
        need(isinstance(names, list) and len(names) == 3, "three components required")
        hashes = []
        for k, name in enumerate(names):
            need(
                isinstance(name, str)
                and Path(name).name == name
                and name.endswith(".bin.gz")
                and name not in paths,
                "invalid or repeated component file",
            )
            paths.add(name)
            sha = read_slab(arm_dir / name)
            need(sha == reference(expert, k), f"wrong bytes for expert {expert} component {k}")
            hashes.append(sha)
        verified.append(dict(keys, components_sha256=hashes))
    return verified


def build_index(events):
    idx, workers = {}, {}
    for seq, row in enumerate(events, 1):
        need(isinstance(row, dict) and FIELDS <= row.keys(), "incomplete event")
        need(all(integer(row[k]) for k in FIELDS - {"kind"}), "noninteger event field")
        kind, e, k, w = (row[x] for x in ("kind", "expert", "component", "worker"))
        need(
            row["seq"] == seq
            and row["ns"] >= 0
            and (seq == 1 or events[seq - 2]["ns"] <= row["ns"]),
            "event sequence or clock",
        )
        need(row["tid"] > 0 and isinstance(kind, str), "thread identity or kind")
        need(
            kind in (*CONTROLLER, *WORKER, *STAGE, *PRIMARY, *DIRECT, *COPY, *ATTACH),
            "unknown event",
        )
        if kind in CONTROLLER:
            need(w == -1, "controller attributed to worker")
        else:
            need(
                w >= 0 and workers.setdefault(w, row["tid"]) == row["tid"],
                "inconsistent worker identity",
            )
        if kind in (*CONTROLLER, *WORKER):
            checks(row, dict(expert=-1, slot=-1, generation=0, ticket=0, component=-1))
        elif kind in STAGE:
            need(e in (1, 2, 3) and row["ticket"] > 0, "stage expert or ticket")
            checks(row, dict(slot=-1, generation=0))
        else:
            allowed = (1,) if kind in ATTACH else (4,) if kind in DIRECT else (1, 4)
            need(e in allowed, "unexpected primary expert")
            checks(row, dict(slot={1: 4, 4: 5}[e], generation=1))
            need((row["ticket"] > 0 if kind in ATTACH else row["ticket"] == 0), "primary ticket")
        need((0 <= k < 3 if kind in READ_COPY else k == -1), "component identity")
        key = (kind, w if kind in WORKER else e, k)
        need(key not in idx, "duplicate event")
        idx[key] = row
    need(len(workers) == len(set(workers.values())) == 4, "four distinct worker TIDs required")
    need(
        not (set(workers.values()) & {row["tid"] for row in events if row["worker"] == -1}),
        "controller reused live worker identity",
    )
    return idx, workers


def verify_journal(events):
    idx, workers = build_index(events)
    used = set()

    def get(kind, e=-1, k=-1):
        key = (kind, e, k)
        need(key in idx, "missing " + str(key))
        used.add(key)
        return idx[key]

    def ordered(*rows):
        s = [r["seq"] for r in rows]
        need(all(a < b for a, b in pairwise(s)), "wrong causal order")

    def same_worker(*rows):
        need(len({r["worker"] for r in rows}) == 1, "work migrated across workers")

    def components(prefix, expert, tidrow):
        records = [
            get(f"{prefix}_{phase}", expert, k) for k in range(3) for phase in ("begin", "end")
        ]
        same_worker(tidrow, *records)
        return records

    tickets = set()
    producers = []
    for e in (1, 2, 3):
        start, end = get("stage_start", e), get("stage_complete", e)
        reads = components("stage_read", e, start)
        ordered(start, *reads, end)
        same_worker(start, end)
        need(all(r["ticket"] == start["ticket"] for r in (*reads, end)), "changed stage ticket")
        tickets.add(start["ticket"])
        producers.append(start["worker"])
    need(len(tickets) == len(set(producers)) == 3, "three concurrent producers required")
    a1, a4 = (get("primary_accept", e) for e in (1, 4))
    p1, p4 = (get("primary_publish", e) for e in (1, 4))
    park, resume, claim = (get(k, 1) for k in ATTACH)
    same_worker(a1, park, resume, claim, p1)
    need(a1["worker"] not in producers, "parked claimant must be the fourth worker")
    need(
        all(r["ticket"] == get("stage_start", 1)["ticket"] for r in (park, resume, claim)),
        "claim lost producer ticket",
    )
    begin, end, returned, finish, drained, shutdown = (get(k) for k in CONTROLLER)
    need(begin["tid"] == end["tid"] == returned["tid"], "remap controller migrated")
    need(finish["tid"] == drained["tid"], "finish controller migrated")
    for e in (1, 2, 3):
        ordered(get("stage_read_begin", e, 0), begin, a1)
    same_worker(get("stage_complete", 2), a4, p4)
    direct = components("direct_read", 4, a4)
    copies4 = components("copy", 4, a4)
    # C305 copies each direct component into its slot before reading the next.
    direct_path = []
    for k in range(3):
        direct_path.extend(direct[2 * k : 2 * k + 2])
        direct_path.extend(copies4[2 * k : 2 * k + 2])
    ordered(a4, *direct_path, p4)
    ordered(
        a1,
        park,
        get("stage_read_end", 2, 0),
        get("stage_complete", 2),
        a4,
        direct[0],
        get("stage_read_end", 1, 0),
        get("stage_complete", 1),
        resume,
        claim,
        *components("copy", 1, a1),
        p1,
        direct[1],
        p4,
        end,
        returned,
        finish,
        get("stage_read_end", 3, 0),
        get("stage_complete", 3),
        drained,
        shutdown,
    )
    for w in workers:
        enter, exit_ = get("worker_enter", w), get("worker_exit", w)
        ordered(enter, shutdown, exit_)
        for record in events:
            if record["worker"] == w and record["kind"] not in WORKER:
                ordered(enter, record, shutdown)
    need(set(idx) == used, "extra event")
    return {
        "workers": len(workers),
        "producer_workers_by_expert": producers,
        "parked_worker": park["worker"],
        "direct_dispatch_worker": a4["worker"],
        "last_publish_seq": p4["seq"],
        "barrier_end_seq": end["seq"],
        "remap_return_seq": returned["seq"],
        "finish_begin_seq": finish["seq"],
        "late_completion_seq": get("stage_complete", 3)["seq"],
        "finish_end_seq": drained["seq"],
    }


def verify(raw: dict, enabled: bool, arm_dir: Path) -> dict:
    """Check one completed arm. The family compares destinations_sha256 across all four."""
    need(isinstance(raw, dict) and type(enabled) is bool, "invalid arm")
    checks(raw.get("counters"), COUNTERS)
    checks(raw.get("terminal"), TERMINAL)
    events = raw.get("events")
    need(isinstance(events, list), "absent journal")
    if enabled:
        witness = verify_journal(events)
    else:
        need(not events, "OFF emitted events")
        witness = None
    destinations = verify_destinations(raw.get("destinations"), Path(arm_dir))
    return {
        "decision": "PASS_NATIVE_MANAGER_FIXTURE_ARM",
        "events": len(events),
        "worker_count_observed": witness["workers"] if witness else 0,
        "schedule": witness,
        "journal_sha256": digest(events),
        "destinations": destinations,
        "destinations_sha256": digest(destinations),
        "counters": dict(COUNTERS),
        "terminal": dict(TERMINAL),
    }
