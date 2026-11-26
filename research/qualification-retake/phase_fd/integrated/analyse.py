"""Verify the sealed C269 journal and price R0's two initial nominal calls."""

import argparse
import collections
import hashlib
import json
import os
import struct
from pathlib import Path

HEADER = struct.Struct("<8s7Q")
RECORD = struct.Struct("<QQQqqq12i")
Row = collections.namedtuple(
    "Row",
    "ns begin gen a b c kind call tile wave layer expert slot worker component fd error reserved",
)
NAMES = (
    "INVALID ENTER RETURN TILE TILE_RETURN SLOT QUEUED_AT_CUT FILE WEIGHT REMAP_BEGIN DEMAND "
    "RESERVE ENQUEUE DISPATCH SKIP READ SET PUBLISH LOAD_FAIL BARRIER_ENTER BARRIER_RETURN "
    "VICTIM_WAIT VICTIM_RESUME REMAP_END WORKER_EXIT END PENDING_AT_RETURN RANKS CANCEL_QUEUED"
).split()


def check(condition, label):
    if not condition:
        raise ValueError(label)


def read_journal(path):
    with Path(path).open("rb") as source:
        raw = source.read(HEADER.size)
        check(len(raw) == HEADER.size, "truncated header")
        magic, version, width, capacity, attempted, saved, flags, reserved = HEADER.unpack(raw)
        check(
            (magic, version, width, capacity, reserved)
            == (b"TESYPF1\0", 1, RECORD.size, 262144, 0),
            "format",
        )
        check(
            flags == 1 and 0 < saved == attempted <= capacity, "unsealed/overflow/invalid journal"
        )
        check(os.fstat(source.fileno()).st_size == HEADER.size + width * saved, "record count")
        data = source.read()
    return [Row(*fields) for fields in RECORD.iter_unpack(data)], {
        "records": saved,
        "flags": flags,
        "journal_sha256": hashlib.sha256(raw + data).hexdigest(),
    }


def union_ns(intervals):
    total = end = 0
    for a, b in sorted(intervals):
        check(0 < a <= b, "interval")
        total += max(0, b - max(a, end))
        end = max(end, b)
    return total


def belady(sequence, initial, slots=40):
    """Offline lower bound after relaxing all simultaneous pins into ordered requests."""
    uses = collections.defaultdict(collections.deque)
    for i, expert in enumerate(sequence):
        uses[expert].append(i)
    cache = set(initial)
    misses = 0
    check(len(cache) <= slots, "cache too large")
    for i, expert in enumerate(sequence):
        check(uses[expert].popleft() == i, "future order")
        if expert not in cache:
            if len(cache) == slots:
                cache.remove(max(cache, key=lambda e: uses[e][0] if uses[e] else len(sequence)))
            cache.add(expert)
            misses += 1
    return misses


def identity(r):
    return (r.layer, r.slot, r.gen, r.expert)


def _audit(rows, header, model=None):
    check(rows and len(rows) == header["records"] and header["flags"] == 1, "header count")
    check(rows[-1].kind == 25, "terminal marker")
    slots, initial, weights, files, calls, stages = {}, {}, {}, {}, {}, {}
    owner, pending, dispatched, components, delivered = {}, {}, {}, {}, set()
    awaiting_initial = set()
    fifo = collections.deque()
    queued_at_return = []
    pending_at_return = set()
    active_call = active_tile = remap = None
    exit_workers = set()
    stats = collections.Counter()
    read_intervals = []
    set_intervals = []
    wait_intervals = []
    reads = []
    sets = []
    ranked = collections.defaultdict(list)
    by_wave = collections.defaultdict(list)
    barrier_start = victim_start = None
    observed_experts = set()
    generation_class, published = {}, {}
    required_at_barrier = []
    last_required = collections.defaultdict(collections.Counter)
    tile_positions = collections.defaultdict(list)

    def settle_boundary():
        check(not queued_at_return and not pending_at_return, "incomplete RETURN snapshot")

    # The startup snapshot holds the manager lock, but an inherited worker can
    # finish a read or a set during the snapshot. Replay those completions after
    # its metadata, preserving the complete live order of all service mutations.
    starts = [i for i, e in enumerate(rows) if e.kind == 1]
    check(starts, "no capture entry")
    first_host = next((i for i, e in enumerate(rows) if e.kind in (2, 3)), len(rows))
    before = rows[:first_host]
    metadata = {1, 5, 6, 7, 8}
    rows = (
        [e for e in before if e.kind in metadata]
        + [e for e in before if e.kind not in metadata]
        + rows[first_host:]
    )
    for index, r in enumerate(rows):
        check(
            0 < r.kind < len(NAMES) and r.reserved == 0 and r.ns > 0 and 0 <= r.begin <= r.ns,
            "record fields",
        )
        event = NAMES[r.kind]
        stats[event] += 1
        key = identity(r)
        physical = (r.layer, r.slot)
        site = (r.call, r.tile, r.layer, r.wave)
        tile_layer = site[:3]
        if event == "ENTER":
            settle_boundary()
            check(active_call is None and r.call == len(calls) + 1 and r.a > 0, "nested call")
            active_call = r.call
            calls[r.call] = {
                "call": r.call,
                "tokens": r.a,
                "tiles": [],
                "start_ns": r.ns,
                "positions": [r.b, r.c],
            }
        elif event == "RETURN":
            check(
                active_call == r.call and active_tile is None and remap is None and r.a == 0,
                "call return",
            )
            check(sum(calls[r.call]["tiles"]) == calls[r.call]["tokens"], "tile token conservation")
            check(r.b == len(fifo) and r.c == len(pending), "RETURN worker/queue totals")
            calls[r.call]["end_ns"] = r.ns
            calls[r.call]["pending_claims"] = len(pending)
            calls[r.call]["queue_length"] = len(fifo)
            queued_at_return = list(fifo)
            pending_at_return = {v[0] for v in slots.values() if v[1] == 1}
            active_call = None
        elif event == "TILE":
            check(
                active_call == r.call
                and active_tile is None
                and r.tile == len(calls[r.call]["tiles"]) + 1,
                "tile order",
            )
            check(0 < r.a <= 32 and (r.b == r.c == -1 or r.c - r.b + 1 == r.a), "tile geometry")
            tile_positions[r.call].append((r.b, r.c))
            calls[r.call]["tiles"].append(r.a)
            active_tile = (r.call, r.tile)
        elif event == "TILE_RETURN":
            check(active_tile == (r.call, r.tile) and remap is None and r.a == 0, "tile return")
            active_tile = None
        elif event == "SLOT":
            check(
                r.call == 1
                and not stages
                and physical not in slots
                and 0 <= r.layer < 36
                and 0 <= r.slot < 40
                and r.a in (0, 1, 2)
                and ((r.expert == -1 and r.a == 0) or (0 <= r.expert < 128 and r.a != 0)),
                "initial slot",
            )
            slots[physical] = (key, r.a)
            initial[physical] = (key, r.a)
            if r.a:
                observed_experts.add((r.layer, r.expert))
            if r.b:
                check(r.a == 1 and r.b == 1, "initial claim")
                pending[key] = None
                awaiting_initial.add(key)
        elif event == "QUEUED_AT_CUT":
            if r.b == 1:
                check(r.call == 1 and r.a == len(fifo) and not stages, "initial queue")
                fifo.append(key)
            else:
                check(
                    r.b == 2 and queued_at_return and queued_at_return.pop(0) == key,
                    "RETURN queue identity",
                )
        elif event == "PENDING_AT_RETURN":
            check(
                r.a == 1 and key in pending_at_return and bool(r.b) == (key in pending),
                "RETURN pending identity",
            )
            pending_at_return.remove(key)
        elif event == "FILE":
            check(r.fd >= 0 and r.fd not in files and r.c & os.O_DIRECT, "file FD")
            files[r.fd] = (r.a, r.b)
        elif event == "WEIGHT":
            role = (r.layer, r.component)
            check(
                0 <= r.layer < 36
                and r.fd in files
                and role not in weights
                and r.a >= 0
                and r.b > 0
                and 0 <= r.component < 3,
                "component metadata",
            )
            weights[role] = (r.fd, r.a, r.b)
        elif event == "REMAP_BEGIN":
            check(
                active_tile == (r.call, r.tile)
                and remap is None
                and site not in stages
                and r.b == 4
                and (r.a == calls[r.call]["tiles"][r.tile - 1] if r.layer != 35 else r.a in (0, 1)),
                "remap entry",
            )
            remap = site
            stages[site] = r.a
        elif event == "RANKS":
            check(
                remap == site and r.wave in (-1, 0) and r.b == len(ranked[tile_layer]), "ranks row"
            )
            ids = tuple((r.a >> (8 * k)) & 255 for k in range(4))
            check(len(set(ids)) == 4 and max(ids) < 128 and 0 <= r.a < 2**32, "top-k IDs")
            ranked[tile_layer].append(ids)
        elif event == "DEMAND":
            check(remap == site and slots[physical][0] == key, "demand generation")
            by_wave[site].append(key)
        elif event == "RESERVE":
            old, state = slots[physical]
            check(
                site == remap
                and state != 1
                and old[3] == r.a
                and r.gen == old[2] + 1
                and key not in owner,
                "reservation",
            )
            slots[physical] = (key, 1)
            owner[key] = (r.call, r.tile)
            pair = (r.layer, r.expert)
            generation_class[key] = "reload" if pair in observed_experts else "first_absent"
            observed_experts.add(pair)
        elif event == "ENQUEUE":
            check(slots[physical] == (key, 1) and r.a in (0, 1, 2) and site == remap, "enqueue")
            fifo.append(key)
        elif event in ("DISPATCH", "SKIP", "CANCEL_QUEUED"):
            check(fifo and fifo.popleft() == key, "FIFO service")
            if event == "DISPATCH":
                check(
                    r.worker in range(4)
                    and key not in pending
                    and r.worker not in pending.values()
                    and slots[physical] == (key, 1),
                    "worker ownership",
                )
                check(owner.get(key, (0, -1)) == (r.call, r.tile), "dispatch origin")
                pending[key] = r.worker
                dispatched[key] = r.worker
            elif event == "SKIP":
                check(slots[physical] != (key, 1) or key in pending, "unexplained skip")
        elif event in ("READ", "SET", "PUBLISH", "LOAD_FAIL"):
            check(
                key in pending
                and r.worker in range(4)
                and owner.get(key, (0, -1)) == (r.call, r.tile),
                "I/O origin",
            )
            if pending[key] is None:
                check(r.worker not in pending.values(), "inherited worker collision")
                pending[key] = r.worker
            check(pending[key] == r.worker, "worker identity")
            if event in ("READ", "SET"):
                fd, base, size = weights[(r.layer, r.component)]
                check(
                    r.fd == fd and r.error == 0 and (r.begin > 0 or key in awaiting_initial),
                    "FD/span or syscall error",
                )
                component = (key, r.component)
                if event == "READ":
                    offset = base + size * r.expert
                    head = offset % 4096
                    aligned = (head + size + 4095) // 4096 * 4096
                    check(
                        component not in components
                        and r.a == offset - head
                        and r.b == aligned
                        and head + size <= r.c <= r.b,
                        "direct read offset/size",
                    )
                    components[component] = r.c
                    reads.append(r)
                    if r.begin:
                        read_intervals.append((r.begin, r.ns))
                else:
                    check(
                        (component in components or key in awaiting_initial)
                        and component not in delivered
                        and r.a == size
                        and r.b == size * r.slot,
                        "payload to slot",
                    )
                    delivered.add(component)
                    sets.append(r)
                    if r.begin:
                        set_intervals.append((r.begin, r.ns))
            else:
                check(
                    event == "PUBLISH" and slots[physical] == (key, 1),
                    "failed or stale publication",
                )
                if key not in awaiting_initial:
                    check(all((key, k) in delivered for k in range(3)), "generation missing copy")
                published[key] = (index, r.ns)
                del pending[key]
                slots[physical] = (key, 2)
        elif event == "BARRIER_ENTER":
            check(site == remap and barrier_start is None and r.a in (0, 1), "barrier entry")
            barrier_start = r
            required_at_barrier = [k for k in by_wave[site] if slots[(k[0], k[1])][1] == 1]
            check(not required_at_barrier or r.a == 1, "barrier would skip required load")
        elif event == "BARRIER_RETURN":
            check(
                site == remap
                and barrier_start is not None
                and barrier_start.a == r.a
                and all(slots[(k[0], k[1])] == (k, 2) for k in by_wave[site]),
                "barrier dependencies",
            )
            if r.a:
                wait_intervals.append((r.call, barrier_start.ns, r.ns))
            if required_at_barrier:
                last = max(required_at_barrier, key=lambda k: published[k][0])
                ns = published[last][1]
                check(barrier_start.ns <= ns <= r.ns, "blocking publication clock")
                category = generation_class.get(last, "inherited")
                clock = last_required[r.call]
                clock[category + "_barriers"] += 1
                clock[category + "_until_publish_ns"] += ns - barrier_start.ns
                clock["publish_to_resume_ns"] += r.ns - ns
            barrier_start = None
        elif event == "VICTIM_WAIT":
            check(remap == site and victim_start is None, "victim wait")
            victim_start = r
        elif event == "VICTIM_RESUME":
            check(remap == site and victim_start is not None, "victim resume")
            wait_intervals.append((r.call, victim_start.ns, r.ns))
            victim_start = None
        elif event == "REMAP_END":
            check(remap == site and barrier_start is None and victim_start is None, "remap return")
            remap = None
        elif event == "WORKER_EXIT":
            check(
                r.worker in range(4)
                and r.worker not in exit_workers
                and r.worker not in pending.values(),
                "worker exit",
            )
            exit_workers.add(r.worker)
        elif event == "END":
            settle_boundary()
            check(
                index == len(rows) - 1 and not pending and not fifo and not any((r.a, r.b, r.c)),
                "service drain",
            )
    check(
        len(initial) == 1440
        and len(weights) == 108
        and len(files) == 1
        and exit_workers == set(range(4))
        and active_call is active_tile is remap is None,
        "incomplete geometry",
    )
    check(
        len({(k[0], k[3]) for k, state in initial.values() if state})
        == sum(state != 0 for _, state in initial.values()),
        "duplicate initial resident/loading",
    )
    if model is not None:
        st = Path(model).stat()
        check(
            set(files.values()) == {(st.st_dev, st.st_ino)}, "FD inode differs from qualified model"
        )
    waves = collections.defaultdict(list)
    for site in stages:
        group = by_wave[site]
        check(len({k[3] for k in group}) == len(group), "duplicate wave demand")
        waves[site[:3]].extend(k[3] for k in group)
    for site, group in waves.items():
        ranks = ranked[site]
        check(
            len(ranks) == stages[(*site, 0) if (*site, 0) in stages else (*site, -1)]
            and set(group) == {e for row in ranks for e in row}
            and len(group) == len(set(group)),
            "rank/demand conservation",
        )
    # C270 supplies one output at the final position of each call. The
    # C281 prompt batch preceding the user span has no output; only the
    # completed prompt requests logits. GPT-OSS selects output rows before FFN35.
    nominal = [c["tokens"] for c in list(calls.values())[:2]] == [5, 148]
    check(all(0 <= site[2] < 36 for site in waves), "layer range")
    for number, call in calls.items():
        for tile, tokens in enumerate(call["tiles"], 1):
            check(
                all(len(ranked[(number, tile, layer)]) == tokens for layer in range(35)),
                "missing routed rows in layers 0-34",
            )
            expected = int(tile == len(call["tiles"]) and not (nominal and number == 1))
            check(len(ranked[(number, tile, 35)]) == expected, "last-layer output mask")
            check(expected == 0 or (number, tile, 35) in waves, "missing final output")
    check(
        stats["REMAP_BEGIN"]
        == stats["REMAP_END"]
        == stats["BARRIER_ENTER"]
        == stats["BARRIER_RETURN"],
        "barrier conservation",
    )
    for number, call in calls.items():
        positions = tile_positions[number]
        check(
            all(
                left[1] + 1 == right[0]
                for left, right in zip(positions, positions[1:], strict=False)
            ),
            "discontinuous inner positions",
        )
        if min(call["positions"]) >= 0:
            check([positions[0][0], positions[-1][1]] == call["positions"], "call position span")
        call["blocking_publications"] = dict(last_required[number])
        call["origin_returned_bytes"] = sum(r.c for r in reads if r.call == number)
        call["origin_payload"] = sum(r.a for r in sets if r.call == number)
        call["origin_loads"] = sum(origin[0] == number for origin in owner.values())
    result = {
        "status": "PASS",
        **header,
        "event_counts": dict(stats),
        "calls": list(calls.values()),
        "initial_claims": len(awaiting_initial),
        "initial_loading": sum(s == 1 for _, s in initial.values()),
        "fd_identity_checked": model is not None,
        "requested": sum(r.b for r in reads),
        "returned": sum(r.c for r in reads),
        "payload": sum(r.a for r in sets),
        "short_usable": sum(r.b != r.c for r in reads),
        "read_starts_before_capture": sum(not r.begin for r in reads),
        "read_worker_ns": sum(b - a for a, b in read_intervals),
        "read_union_ns": union_ns(read_intervals),
        "set_worker_ns": sum(b - a for a, b in set_intervals),
        "set_union_ns": union_ns(set_intervals),
        "wait_union_ns": union_ns([(a, b) for _, a, b in wait_intervals]),
    }
    if [c["tokens"] for c in list(calls.values())[:2]] == [5, 148]:
        end = calls[2]["end_ns"]
        start = calls[1]["start_ns"]
        floor = constrained = absent = offline = 0
        for layer in range(36):
            initial_ids = {k[3] for k, state in initial.values() if k[0] == layer and state}
            sequence = [
                k[3]
                for site in stages
                if site[0] in (1, 2) and site[2] == layer
                for k in by_wave[site]
            ]
            unique = len(set(sequence) - initial_ids)
            minimum = belady(sequence, initial_ids)
            size = sum(weights[(layer, i)][2] for i in range(3))
            floor += unique * size
            constrained += minimum * size
            absent += unique
            offline += minimum
        # Exclude the inter-call gap when computing wall unions.
        windows = [(calls[c]["start_ns"], calls[c]["end_ns"]) for c in (1, 2)]

        def overlap(span):
            return [
                (max(a, s), min(b, t)) for a, b in span for s, t in windows if min(b, t) > max(a, s)
            ]

        result["nominal_prefill"] = {
            "compulsory_unique": absent,
            "compulsory_payload_floor": floor,
            "relaxed_40slot_load_floor": offline,
            "relaxed_40slot_payload_floor": constrained,
            "origin_returned_bytes": sum(r.c for r in reads if r.call in (1, 2)),
            "completed_in_calls_returned_bytes": sum(
                r.c for r in reads if any(a <= r.ns <= b for a, b in windows)
            ),
            "returned_after_prefill_for_origin_bytes": sum(
                r.c for r in reads if r.call in (1, 2) and r.ns > end
            ),
            "origin_payload": sum(r.a for r in sets if r.call in (1, 2)),
            "origin_dispatched": sum(owner.get(k, (0, -1))[0] in (1, 2) for k in dispatched),
            "read_union_in_calls_ns": union_ns(overlap(read_intervals)),
            "set_union_in_calls_ns": union_ns(overlap(set_intervals)),
            "wait_union_in_calls_ns": union_ns(
                [(a, b) for c, a, b in wait_intervals if c in (1, 2)]
            ),
            "two_calls_span_ns": end - start,
            "two_calls_union_ns": union_ns(windows),
        }
    return result


def audit(records, header, model=None):
    try:
        return _audit(records, header, model)
    except (ValueError, KeyError, IndexError) as exc:
        return {"status": "FAIL", "gate": str(exc), **header}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=Path)
    parser.add_argument("--model", type=Path)
    args = parser.parse_args()
    records, header = read_journal(args.journal)
    result = audit(records, header, args.model)
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(result["status"] != "PASS")
