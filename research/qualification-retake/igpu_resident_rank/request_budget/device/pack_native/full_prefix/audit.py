"""Authenticate T1 ranks and victims and the subsequent full packed T2."""

import hashlib
import os
import stat
import struct
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
NAT = run_path(str(HERE.parent / "natural_trace/analyse.py"))
JOBS = run_path(str(HERE.parent / "natural_trace/jobs.py"))
PFJ = NAT["PFJ"]
HEADER, RECORD, Row, check = (PFJ[k] for k in ("HEADER", "RECORD", "Row", "check"))
CAP, T2_CAP = 1_398_100, 262_144
T1 = [61] + [256] * 7 + [190] + [1] * 77
NUMERIC = [189] + [1] * 32
MAGIC = b"TESYFP1\0"
META = {5, 7, 8, 29}


def max_prefix_records():
    tiles = [min(n - offset, 32) for n in T1 for offset in range(0, n, 32)]
    ranks = sum(tiles) * 36
    demand = sum(min(128, 4 * n) for n in tiles) * 36
    preload = sum(max(0, min(128, 4 * n) - 18) for n in tiles if n * 4 > 40) * 36
    # One descriptor per slot and weight, two O_DIRECT files; no other per-job T1 events.
    return 2 * (len(T1) + len(tiles)) + 1440 + 108 + 2 + ranks + 2 * (demand + preload)


def metadata(path, closed):
    p = Path(path)
    with p.open("rb") as f:
        s = os.fstat(f.fileno())
        check(
            not p.is_symlink() and stat.S_ISREG(s.st_mode) and stat.S_IMODE(s.st_mode) == 0o600,
            "private regular PFJ",
        )
        raw = f.read(HEADER.size)
        check(len(raw) == HEADER.size, "incomplete PFJ header")
        magic, version, width, capacity, attempted, saved, flags, cut = HEADER.unpack(raw)
        check((magic, version, width, capacity) == (MAGIC, 1, RECORD.size, CAP), "profile format")
        if closed:
            check(
                flags == 1
                and attempted == saved
                and 0 < saved <= CAP
                and s.st_size == HEADER.size + saved * width,
                "invalid final counts, flags or extent",
            )
        else:
            check(
                (attempted, saved, flags) == (0, 0, 0) and s.st_size == HEADER.size + CAP * width,
                "provisional header or extent",
            )
        check(
            cut == 0 or (0 < cut <= max_prefix_records() and cut + T2_CAP <= CAP),
            "invalid prefix limit or insufficient space for full T2",
        )
        return cut, saved


def iter_rows(path, start, count):
    # Stream the bounded prefix repeatedly; each pass uses at most 1024 records of input storage.
    with Path(path).open("rb") as f:
        f.seek(HEADER.size + start * RECORD.size)
        while count:
            n = min(count, 1024)
            raw = f.read(n * RECORD.size)
            check(len(raw) == n * RECORD.size, "truncated record sequence")
            yield from (Row(*fields) for fields in RECORD.iter_unpack(raw))
            count -= n


def snapshot_fd(files, pack, model):
    check(set(files) == {7, 29} and files[7][0] != files[29][0], "two distinct data FDs")
    for kind, source in ((7, model), (29, pack)):
        _, dev, ino, flags = files[kind]
        check(
            flags & os.O_DIRECT and (source is None or (dev, ino) == JOBS["inode"](source)),
            "data FD must be O_DIRECT on the authenticated inode",
        )
    check(files[7][1:3] != files[29][1:3], "same data inode")


def prefix_grade(rows, geometry, first_output_call, pack=None, model=None, final=False):
    slots, present, files, weights = {}, set(), {}, set()
    ranked = defaultdict(int)
    routes, content = hashlib.sha256(), hashlib.sha256()
    seq, visits = Counter(), Counter()
    open_call = tile = None
    position = next_call = 0
    counts = Counter()
    active = {}
    finished = False
    for r in rows:
        check(
            not finished and r.ns > 0 and 0 <= r.begin <= r.ns and r.reserved == 0,
            "prefix record integrity",
        )
        content.update(RECORD.pack(*r))
        counts[r.kind] += 1
        site = (r.call, r.tile, r.layer)
        ix = r.layer, r.slot
        key = r.layer, r.expert
        if r.kind == 1:
            next_call += 1
            check(
                open_call is None
                and tile is None
                and r.call == next_call <= len(geometry)
                and r.a == geometry[r.call - 1]
                and (r.b, r.c) in ((-1, -1), (position, position + r.a - 1)),
                "call lineage",
            )
            open_call = r.call
        elif r.kind == 2:
            check(
                r.call == open_call
                and tile is None
                and r.a == 0
                and r.b >= 0
                and r.c in range(5)
                and seq[r.call] == (geometry[r.call - 1] + 31) // 32,
                "incomplete call",
            )
            if r.call == len(geometry):
                check(not active and r.b == r.c == 0, "T1 terminal RETURN must be drained")
            open_call = None
        elif r.kind == 3:
            check(
                r.call == open_call
                and tile is None
                and r.tile == seq[r.call] + 1
                and r.a == min(32, geometry[r.call - 1] - 32 * seq[r.call])
                and (r.b, r.c) == (position, position + r.a - 1),
                "tile coverage",
            )
            check(
                len(slots) == 1440 and len(weights) == 108 and len(files) == 2,
                "initial snapshot incomplete before first tile",
            )
            seq[r.call] += 1
            tile = r
            visits.clear()
            position += r.a
        elif r.kind == 4:
            check(
                tile is not None and (r.call, r.tile, r.a) == (tile.call, tile.tile, 0),
                "tile return",
            )
            last_tile = 32 * r.tile >= geometry[r.call - 1]
            required = int(last_tile and r.call >= first_output_call)
            for layer in range(36):
                check(
                    ranked[r.call, r.tile, layer] == (required if layer == 35 else tile.a),
                    "missing/duplicated rank row or wrong pruning",
                )
            tile = None
        elif r.kind in META:
            check((open_call, r.call, len(seq), tile) == (1, 1, 0, None), "misplaced initial data")
            if r.kind == 5:
                check(
                    r.layer in range(36)
                    and r.slot in range(40)
                    and ix not in slots
                    and r.b == 0
                    and (
                        r.expert == -1
                        if r.a == 0
                        else r.a == 2 and r.expert in range(128) and key not in present
                    ),
                    "initial slot binding/state",
                )
                slots[ix] = (r.expert, r.gen, r.a)
                if r.a:
                    present.add(key)
            elif r.kind == 8:
                k = r.layer, r.component
                check(
                    k not in weights
                    and r.layer in range(36)
                    and r.component in range(3)
                    and 7 in files
                    and r.fd == files[7][0]
                    and r.b == 4_406_400
                    and r.a >= 0,
                    "weight component",
                )
                weights.add(k)
            else:
                check(r.kind not in files and r.fd >= 0, "duplicate FD")
                files[r.kind] = r.fd, r.a, r.b, r.c
        elif r.kind == 27:
            check(
                tile is not None
                and (r.call, r.tile) == (tile.call, tile.tile)
                and r.layer in range(36)
                and r.wave in (-1, 0)
                and r.b == ranked[site]
                and 0 <= r.a < 2**32,
                "rank row ordinal",
            )
            ids = r.a.to_bytes(4, "little")
            check(len(set(ids)) == 4 and max(ids) < 128, "rank quartet")
            visits.update((r.layer, e) for e in ids)
            ranked[site] += 1
            routes.update(struct.pack("<5I", r.call, r.tile, r.layer, r.b, r.a))
        elif r.kind == 11:
            check(
                tile is not None
                and (r.call, r.tile) == (tile.call, tile.tile)
                and key in visits
                and ix in slots
                and key not in present
                and ix not in active,
                "reservation",
            )
            old, gen, state = slots[ix]
            check(old == r.a and r.gen == gen + 1 and state in (0, 2), "victim/old generation")
            if state == 2:
                present.remove((r.layer, old))
            present.add(key)
            active[ix] = (r.call, r.tile, r.wave, r.expert, r.gen)
            slots[ix] = (r.expert, r.gen, 1)
        elif r.kind == 17:
            check(
                r.worker in range(4)
                and active.pop(ix, None) == (r.call, r.tile, r.wave, r.expert, r.gen),
                "absent/late/duplicated publication",
            )
            slots[ix] = (r.expert, r.gen, 2)
        elif final and r.kind == 24:
            check(
                not active
                and open_call is None
                and next_call == len(geometry)
                and r.worker in range(4)
                and counts[25] == 0,
                "worker lifecycle",
            )
            counts[f"exit{r.worker}"] += 1
        elif final and r.kind == 25:
            check(
                (r.a, r.b, r.c) == (0, 0, 0) and all(counts[f"exit{w}"] == 1 for w in range(4)),
                "failed/missing drain",
            )
            finished = True
        else:
            raise ValueError(f"unexpected prefix record kind {r.kind}")
    check(
        not active
        and open_call is tile is None
        and next_call == len(geometry)
        and position == sum(geometry)
        and finished == final
        and counts[11] == counts[17],
        "prefix stop",
    )
    if geometry == T1:
        check(
            len(slots) == 1440 and all(s[2] == 2 for s in slots.values()),
            "all READY at natural cut",
        )
    snapshot_fd(files, pack, model)
    result = dict(
        sha256=content.hexdigest(),
        route_sha256=routes.hexdigest(),
        calls=next_call,
        tiles=sum(seq.values()),
        ranks=counts[27],
        reserves=counts[11],
        publications=counts[17],
        first_position=0,
        last_position=position - 1,
        prefill_calls=list(range(1, first_output_call + 1)),
        fds={
            ("pack" if k == 29 else "model"): {"fd": v[0], "dev": v[1], "ino": v[2]}
            for k, v in files.items()
        },
    )
    return result, slots


def seal_before_post(journal, pack_identity=None, model_identity=None):
    cut, _ = metadata(journal, False)
    check(cut > 0, "native T1 cut has not been published")
    grade, _ = prefix_grade(iter_rows(journal, 0, cut), T1, 9, pack_identity, model_identity)
    return iter_rows(journal, 0, cut), grade | {"records": cut, "bytes": cut * RECORD.size}


def audit_numeric(path, pack_identity, model_identity):
    cut, count = metadata(path, True)
    check(cut == 0, "unexpected natural cut in C292")
    grade, _ = prefix_grade(
        iter_rows(path, 0, count), NUMERIC, 1, pack_identity, model_identity, True
    )
    with Path(path).open("rb") as raw:
        digest = hashlib.file_digest(raw, "sha256").hexdigest()
    return grade | {
        "status": "PASS_FULL_PREFIX_C292_JOURNAL",
        "enabled": True,
        "records": count,
        "journal_sha256": digest,
    }


def audit_closed(path, seal, pack_identity, model_identity):
    cut, count = metadata(path, True)
    check(cut == seal["records"] and 0 < count - cut <= T2_CAP, "T1 cut or T2 capacity")
    grade, slots = prefix_grade(iter_rows(path, 0, cut), T1, 9, pack_identity, model_identity)
    check(
        all(grade[k] == seal[k] for k in grade) and seal["bytes"] == cut * RECORD.size,
        "sealed T1 changed after POST",
    )
    rows = [
        r._replace(call=r.call - len(T1)) if r.call else r
        for r in iter_rows(path, cut, count - cut)
    ]
    check(rows[0].kind == 1 and rows[0].call == 1 and rows[0].a == 5, "T2 first ENTER")
    live = {(r.layer, r.slot): (r.expert, r.gen, r.a) for r in rows if r.kind == 5}
    check(live == slots, "different live slot snapshot across POST")
    jobs = JOBS["audit_jobs"](rows, pack_identity, model_identity)
    check(jobs["status"] == "COMPLETE" and jobs["eligible_clean_run"], "incomplete T2 service")
    host = NAT["host_trace"](rows)
    check(
        host["route"] == NAT["read"](NAT["HERE"] / "historical.json")["route"], "T2 ordered route"
    )
    return dict(
        status="PASS_FULL_PREFIX_NATURAL_JOURNAL",
        t1=grade,
        t2_jobs=jobs,
        t2_route=host["route"],
        t2_records=count - cut,
        t2_enter_ns=host["calls"][0]["enter_ns"],
    )
