"""Join the synthetic projector to the actual C291 uniwave lookups and completed jobs."""

import hashlib
import json
import os
from collections import Counter, defaultdict, deque
from pathlib import Path
from runpy import run_path

PFJ = run_path(str(Path(__file__).resolve().parents[2] / "phase_fd/integrated/analyse.py"))
check, identity = PFJ["check"], PFJ["identity"]
TILES = ((5,), (32, 32, 32, 32, 20), (1,))
FIRST = 2044
STATES = ("absent", "loading", "ready")


def quartet(value):
    ids = tuple((value >> (8 * i)) & 255 for i in range(4))
    check(0 <= value < 2**32 and max(ids) < 128 and len(set(ids)) == 4, "invalid quartet")
    return ids


def site_of(e):
    return e.call, e.tile, e.layer


def checked_geometry(rows):
    expected = {}
    pos = FIRST
    for call, tiles in enumerate(TILES, 1):
        for tile, count in enumerate(tiles, 1):
            expected[call, tile] = (pos, pos + count - 1)
            pos += count
    call_events = [(e.kind, e.call, e.a, e.b, e.c) for e in rows if e.kind in (1, 2)]
    expected_calls = []
    for call, tiles in enumerate(TILES, 1):
        expected_calls.extend(
            [
                (1, call, sum(tiles), expected[call, 1][0], expected[call, len(tiles)][1]),
                (2, call, 0, 0, 0),
            ]
        )
    check(call_events == expected_calls, "external returns or positions")
    positions, tile_spans = defaultdict(list), {}
    call = tile = None
    for i, e in enumerate(rows):
        if e.kind == 1:
            check(call is None, "nested call")
            call = e.call
        elif e.kind == 2:
            check(tile is None and call == e.call, "call boundary")
            call = None
        elif e.kind == 3:
            key = (e.call, e.tile)
            check(tile is None and key in expected and e.call == call, "tile open")
            lo, hi = expected[key]
            check((e.a, e.b, e.c) == (hi - lo + 1, lo, hi), "tile positions")
            check(key not in tile_spans, "duplicate tile")
            tile, begin = key, i
        elif e.kind == 4:
            check(tile == (e.call, e.tile) and e.a == 0, "tile return")
            tile_spans[tile] = begin, i
            tile = None
        elif e.kind == 31:
            check(tile == (e.call, e.tile) and e.layer == e.wave == -1, "ROW scope")
            lo, hi = expected[tile]
            row = len(positions[tile])
            selected = int(e.b == hi and e.tile == len(TILES[call - 1]))
            check(e.a == row and e.b == lo + row <= hi and e.c == selected, "ROW position/mask")
            positions[tile].append((i, e))
        elif e.kind in (9, 10, 19, 20, 23, 27, 32, 33, 34):
            check(tile == (e.call, e.tile) and e.layer in (1, 35) and e.wave == -1, "target scope")
    check(list(tile_spans) == list(expected) and call is tile is None, "incomplete tile sequence")
    result = {}
    for key, (lo, hi) in expected.items():
        tile_rows = positions[key]
        check(len(tile_rows) == hi - lo + 1, "incomplete rows")
        result[(*key, 1)] = tile_rows
        selected = [r for r in tile_rows if r[1].c]
        if selected:
            result[(*key, 35)] = selected
    return result


def check_service(rows):
    """Replay ownership in journal order. Worker wall intervals may overlap across jobs."""
    slots, weights, owner, live, jobs, looked = {}, {}, {}, {}, {}, {}
    fifo = deque()
    clocks = defaultdict(list)
    exited = set()
    file_rows = [e for e in rows if e.kind == 7]
    check(
        len(file_rows) == 1 and file_rows[0].fd >= 0 and file_rows[0].c & os.O_DIRECT,
        "GGUF descriptor",
    )
    fd = file_rows[0].fd
    for i, e in enumerate(rows):
        key = identity(e)
        place = e.layer, e.slot
        site_key = (*site_of(e), e.expert)
        if e.kind == 5:
            check(place not in slots and (e.expert, e.a, e.b) == (-1, 0, 0), "cold slot snapshot")
            slots[place] = (key, 0)
        elif e.kind == 8:
            check(
                (e.layer, e.component) not in weights and e.fd == fd and e.b == 128, "GGUF weight"
            )
            weights[e.layer, e.component] = e.a
        elif e.kind == 34:
            binding = owner.get((e.layer, e.expert))
            check(site_key not in looked and 0 <= e.expert < 128 and e.c == 0, "duplicate lookup")
            if binding is None:
                check((e.slot, e.gen, e.a, e.b) == (-1, 0, 0, 0), "absent lookup binding")
            else:
                check(binding == key and slots[place] == (key, e.a), "lookup owner/state")
                check(e.a in (1, 2) and e.b == int(key in live.values()), "lookup claim/state")
            looked[site_key] = (i, e)
        elif e.kind == 11:
            check(
                site_key in looked and looked[site_key][1].a == 0,
                "reservation without absent lookup",
            )
            old, state = slots[place]
            check(
                state != 1 and e.a == old[3] and e.gen == old[2] + 1,
                "reservation victim/generation",
            )
            if state:
                del owner[e.layer, old[3]]
            check((e.layer, e.expert) not in owner and key not in jobs, "duplicate owner")
            slots[place] = (key, 1)
            owner[e.layer, e.expert] = key
            jobs[key] = [e]
        elif e.kind == 12:
            check(slots.get(place) == (key, 1) and e.a in (0, 1), "enqueue binding")
            check(site_key in looked, "enqueue without lookup")
            check(e.a == int(looked[site_key][1].a == 1), "enqueue reason")
            fifo.append(key)
        elif e.kind in (13, 14):
            check(fifo and fifo.popleft() == key, "FIFO dispatch")
            if e.kind == 14:
                check(slots[place] != (key, 1) or key in live.values(), "unexplained skip")
                continue
            check(
                e.worker in range(4) and e.worker not in live and key not in live.values(),
                "exclusive claim",
            )
            check(slots[place] == (key, 1) and len(jobs[key]) == 1, "dispatch generation")
            check(
                site_of(e) == site_of(jobs[key][0]) and e.wave == jobs[key][0].wave, "claim origin"
            )
            live[e.worker] = key
            jobs[key].append(e)
        elif e.kind in (15, 16, 17):
            check(live.get(e.worker) == key and slots[place] == (key, 1), "stale worker")
            job = jobs[key]
            check(site_of(e) == site_of(job[0]) and e.wave == job[0].wave, "job origin")
            expected = (15, 16, 15, 16, 15, 16, 17)
            step = len(job) - 2
            check(
                0 <= step < len(expected) and e.kind == expected[step],
                "three ordered READ/SET pairs",
            )
            if e.kind != 17:
                role = step // 2
                check(e.component == role and e.fd == fd and e.error == 0, "component/FD")
                check(job[-1].ns <= e.begin <= e.ns, "within-worker clock")
                if e.kind == 15:
                    offset = weights[e.layer, role] + 128 * e.expert
                    check(e.a == offset - offset % 4096 and e.b == 4096, "GGUF direct window")
                    check(offset % 4096 + 128 <= e.c <= e.b, "read did not cover payload")
                else:
                    check((e.a, e.b, e.c) == (128, 128 * e.slot, 0), "SET payload/destination")
                clocks[e.kind].append((e.begin, e.ns))
            else:
                check(job[-1].ns <= e.ns, "publication clock")
                slots[place] = (key, 2)
                del live[e.worker]
            job.append(e)
        elif e.kind == 10:
            check(
                site_key in looked and slots[place][0] == key and owner[e.layer, e.expert] == key,
                "demand binding",
            )
        elif e.kind == 20:
            for k, (_, hit) in looked.items():
                if k[:3] == site_of(e):
                    binding = owner[hit.layer, hit.expert]
                    check(slots[hit.layer, binding[1]] == (binding, 2), "barrier before READY")
        elif e.kind == 19:
            waiting = any(k[:3] == site_of(e) and v.a != 2 for k, (_, v) in looked.items())
            check(e.a == int(waiting), "barrier inconsistent with lookup")
        elif e.kind == 24:
            check(
                e.worker in range(4) and e.worker not in live and e.worker not in exited,
                "worker exit",
            )
            exited.add(e.worker)
    check(set(slots) == {(layer, s) for layer in range(36) for s in range(40)}, "slot coverage")
    check(set(weights) == {(layer, r) for layer in range(36) for r in range(3)}, "weight coverage")
    check(not fifo and not live and exited == set(range(4)), "worker drain")
    check(all(job[-1].kind == 17 for job in jobs.values()), "unpublished reservation")
    return jobs, looked, clocks


def join_site(events, tile_rows):
    """Compare same-row suggestions with gold, then deduplicate by authoritative lookup."""
    by_kind = defaultdict(list)
    for i, e in events:
        by_kind[e.kind].append((i, e))
    for kind in (9, 19, 20, 23, 32):
        check(len(by_kind[kind]) == 1, "missing/duplicate site delimiter")
    (ib, beg), (iw, wait), (ir, resume), (ie, end) = [by_kind[k][0] for k in (9, 19, 20, 23)]
    start_i, start = by_kind[32][0]
    check(ib < iw < ir < ie and beg.ns <= wait.ns <= resume.ns <= end.ns, "callback/barrier order")
    check(wait.a == resume.a and wait.a in (0, 1), "barrier decision")
    check((beg.a, beg.b) == (len(tile_rows), 4), "official shape")
    check(
        (start.a, start.b, start.c) == (beg.layer - 1, 24 * len(tile_rows), 144),
        "projector origin/cost",
    )
    check(len(by_kind[27]) == len(by_kind[33]) == len(tile_rows), "row conservation")
    mapped = {row.a: (ri, row) for ri, row in tile_rows}
    pred = {}
    for i, e in by_kind[33]:
        check(e.b in mapped and e.b not in pred, "row binding")
        ri, row = mapped[e.b]
        check(
            row.b == e.c and ri < i and start_i < i and start.ns <= e.ns,
            "prediction position/release",
        )
        pred[e.b] = (i, e.ns, set(quartet(e.a)))
    lookup = {}
    for i, e in by_kind[34]:
        check(ib < i < iw and e.expert not in lookup, "lookup scope")
        lookup[e.expert] = (i, e)
    demanded = {}
    for i, e in by_kind[10]:
        check(
            ib < i < iw and e.expert not in demanded and e.expert in lookup,
            "duplicate/foreign demand",
        )
        check(lookup[e.expert][0] < i, "demand before lookup")
        demanded[e.expert] = identity(e)
    check(demanded.keys() == lookup.keys(), "lookup/demand conservation")
    checks, eligible, official = Counter(), set(), set()
    early_before_lookup = set()
    leads, native_rows = [], []
    for j, ((i, ranks), (_, row)) in enumerate(zip(by_kind[27], tile_rows, strict=True)):
        check(
            ib < i < min(v[0] for v in lookup.values()) and ranks.b == j, "ranks outside callback"
        )
        ordered = quartet(ranks.a)
        true = set(ordered)
        check(true <= demanded.keys(), "foreign rank")
        native_rows.append([row.b, beg.layer, list(ordered), [demanded[e][1] for e in ordered]])
        pi, stamp, guess = pred[row.a]
        official |= true
        matched = true & guess
        checks["matched_rank_offers"] += len(matched)
        checks["false_rank_offers"] += 4 - len(matched)
        if pi >= ib:
            checks["available_after_remap_rows"] += 1
        for expert in matched:
            li, event = lookup[expert]
            check(
                (pi < li and stamp <= event.ns) or (pi > li and stamp >= event.ns), "lookup clock"
            )
            if pi < li:
                early_before_lookup.add(expert)
            if pi < ib:
                check(stamp <= beg.ns, "remap clock")
                eligible.add(expert)
                leads.append(event.ns - stamp)
    check(official == set(demanded), "ranks/demand keys")
    absent = {demanded[e] for e in eligible if lookup[e][1].a == 0}
    states = Counter(STATES[lookup[e][1].a] for e in lookup)
    timely = Counter(STATES[lookup[e][1].a] for e in eligible)
    return (
        {
            "rank_rows": len(tile_rows),
            "matched_rank_offers": checks["matched_rank_offers"],
            "false_rank_offers": checks["false_rank_offers"],
            "available_after_remap_rows": checks["available_after_remap_rows"],
            "before_lookup_distinct_matched_keys": len(early_before_lookup),
            "state_at_lookup": dict(states),
            "early_matched_keys_by_lookup_state": dict(timely),
            "min_lookup_lead_ns": min(leads, default=None),
            "max_lookup_lead_ns": max(leads, default=None),
            "projection_activation_bytes": start.b,
            "projection_coefficient_bytes": start.c,
            "projector_start_to_last_available_ns": max(e.ns for _, e in by_kind[33]) - start.ns,
            "barrier_interval_ns": resume.ns - wait.ns,
        },
        absent,
        native_rows,
    )


def audit_rows(rows):
    allowed = {
        1,
        2,
        3,
        4,
        5,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        19,
        20,
        23,
        24,
        25,
        27,
        31,
        32,
        33,
        34,
    }
    check(
        rows
        and all(
            r.kind in allowed and r.reserved == 0 and 0 <= r.begin <= r.ns and r.ns > 0
            for r in rows
        ),
        "unexpected event or failed service",
    )
    check(
        rows[-1].kind == 25
        and sum(r.kind == 25 for r in rows) == 1
        and (rows[-1].a, rows[-1].b, rows[-1].c) == (0, 0, 0),
        "terminal drain",
    )
    geometry = checked_geometry(rows)
    jobs, looked, clocks = check_service(rows)
    events = defaultdict(list)
    for i, e in enumerate(rows):
        if e.kind in (9, 10, 19, 20, 23, 27, 32, 33, 34):
            events[site_of(e)].append((i, e))
    check(events.keys() == geometry.keys(), "mask/target coverage")
    sites, credit, state_counts = [], set(), Counter()
    native_rows = []
    for (call, tile, layer), members in geometry.items():
        site, nominated, resolved = join_site(events[call, tile, layer], members)
        check(
            credit.isdisjoint(nominated) and nominated <= jobs.keys(),
            "multiple credits or no service",
        )
        credit |= nominated
        native_rows.extend(resolved)
        state_counts.update(site["state_at_lookup"])
        late = site["available_after_remap_rows"]
        check(late == int((call, tile, layer) == (3, 1, 1)), "late-result fixture")
        if late:
            order = {e.kind: i for i, e in events[call, tile, layer]}
            check(order[33] > order[23] and order[32] < order[9], "late fault placement")
        sites.append({"call": call, "tile": tile, "layer": layer, **site})
    check(
        state_counts["absent"] == len(jobs) and len(looked) == sum(state_counts.values()),
        "claimed jobs vs lookups",
    )
    check(
        state_counts["ready"] and credit and sum(s["false_rank_offers"] for s in sites),
        "missing fixture contrasts",
    )

    def volume(keys):
        reads = [e for key in keys for e in jobs[key] if e.kind == 15]
        sets = [e for key in keys for e in jobs[key] if e.kind == 16]
        return {
            "jobs": len(keys),
            "reads": len(reads),
            "sets": len(sets),
            "requested_bytes": sum(e.b for e in reads),
            "returned_bytes": sum(e.c for e in reads),
            "logical_payload_bytes": sum(e.a for e in sets),
            "set_bytes": sum(e.a for e in sets),
        }

    spans = clocks[15] + clocks[16]
    return {
        "status": "PASS_ROUTER_OBSERVATION_JOIN",
        "official_rows_sha256": hashlib.sha256(
            json.dumps(native_rows, separators=(",", ":")).encode()
        ).hexdigest(),
        "input_rows": sum(map(sum, TILES)),
        "rows": sum(s["rank_rows"] for s in sites),
        "sites": sites,
        "matched_rank_offers": sum(s["matched_rank_offers"] for s in sites),
        "early_absent_generations": len(credit),
        "state_at_lookup": dict(state_counts),
        "service": volume(jobs),
        "early_absent_service": volume(credit),
        "service_worker_ns": sum(b - a for a, b in spans),
        "service_union_ns": PFJ["union_ns"](spans),
        "shadow_dispatched_jobs": 0,
        "measured_saved_bytes": 0,
        "speedup": None,
    }


def audit(path):
    rows, header = PFJ["read_journal"](path)
    return header | audit_rows(rows)
