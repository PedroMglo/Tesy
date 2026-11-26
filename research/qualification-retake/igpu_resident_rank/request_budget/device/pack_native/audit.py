"""Reconcile the packed and original C291 CPU fixture against its sealed PFJ journal."""

import argparse
import errno
import json
import os
from collections import Counter, deque
from pathlib import Path
from runpy import run_path

INTEGRATED = Path(__file__).resolve().parents[4] / "phase_fd/integrated"
pfj = run_path(str(INTEGRATED / "analyse.py"))
check, identity = pfj["check"], pfj["identity"]
read_journal, union_ns = pfj["read_journal"], pfj["union_ns"]

SLAB = 4_406_400
STRIDE = 13_258_752
WINDOW = 13_221_888
ALIGN = 4096
READ, SET, PUBLISH, FAIL = 15, 16, 17, 18
PACK_FILE, PACK_READ = 29, 30


def check_job(events, *, packed, short, files, weights):
    claim, *service, finish = events
    reads, sets = [], []
    expected_roles = [] if short else [0, 1, 2]
    previous = claim.ns
    for e in service:
        check(previous <= e.begin <= e.ns, "overlap within one claimed job")
        previous = e.ns
        if e.kind == SET:
            role = len(sets)
            check(role in expected_roles and e.component == role, "component order")
            check(e.a == SLAB and e.b == e.slot * SLAB, "destination slot/length")
            check(e.c == (role * SLAB if packed else 0) and e.error == 0, "component source")
            check(e.fd == files[PACK_FILE if packed else 7].fd, "copy FD")
            sets.append(e)
        else:
            check(e.kind == (PACK_READ if packed else READ), "byte source")
            check(e.fd == files[PACK_FILE if packed else 7].fd, "read FD")
            if packed:
                check(e.component == -1 and e.b == WINDOW, "packed range")
                check(e.a == STRIDE * (e.layer * 128 + e.expert), "packed offset")
            else:
                check(len(reads) < 3 and e.component == len(reads), "GGUF component")
                wt = weights[e.layer, e.component]
                offset = wt.a + e.expert * SLAB
                head = offset % ALIGN
                check(wt.b == SLAB and wt.fd == e.fd, "GGUF geometry")
                check(
                    e.a == offset - head and e.b == (head + SLAB + ALIGN - 1) // ALIGN * ALIGN,
                    "GGUF range",
                )
                check(head + SLAB <= e.c <= e.b and e.error == 0, "GGUF incomplete")
            reads.append(e)
    check(previous <= finish.ns and finish.kind == (FAIL if short else PUBLISH), "completion")
    check([e.component for e in sets] == expected_roles, "incomplete delivery")
    if packed:
        check(bool(reads), "missing packed read")
        check(all(e.c == -1 and e.error == errno.EINTR for e in reads[:-1]), "unexpected retry")
        last = reads[-1]
        check(last.error == 0 and 0 <= last.c <= last.b, "packed syscall")
        check(last.c == (3 * SLAB - 1 if short else WINDOW), "controlled syscall return")
        check(service == reads + sets, "publish before all packed components")
    else:
        check([e.kind for e in service] == [READ, SET] * 3, "GGUF component pairing")
    return reads, sets


def reconcile(rows, *, packed, short=False):
    """The fixture starts with no in-flight work and drives one layer of a 36-layer manager."""
    check(not short or packed, "unknown fault arm")
    kinds = Counter(e.kind for e in rows)
    check(rows and kinds[25] == 1 and rows[-1].kind == 25, "terminal marker")
    check((rows[-1].a, rows[-1].b, rows[-1].c) == (0, 0, int(short)), "undrained run")
    exits = [e.worker for e in rows if e.kind == 24]
    check(sorted(exits) == list(range(4)), "worker exits")
    check(kinds[5] == 36 * 40 and kinds[8] == 36 * 3, "entry snapshot coverage")
    check(kinds[7] == 1 and kinds[PACK_FILE] == int(packed), "file identities")
    files = {e.kind: e for e in rows if e.kind in (7, PACK_FILE)}
    for f in files.values():
        check(f.fd >= 0 and f.b > 0 and f.c & os.O_DIRECT, "direct descriptor")
    if packed:
        p, g = files[PACK_FILE], files[7]
        check(p.fd != g.fd and (p.a, p.b) != (g.a, g.b), "pack aliases GGUF")
    weights = {(e.layer, e.component): e for e in rows if e.kind == 8}
    check(
        set(weights) == {(layer, role) for layer in range(36) for role in range(3)},
        "weight metadata",
    )
    slots = {(e.layer, e.slot): (e.expert, e.gen) for e in rows if e.kind == 5}
    check(
        set(slots) == {(layer, slot) for layer in range(36) for slot in range(40)}, "slot metadata"
    )

    reserved, claimed, live, jobs = {}, {}, {}, {}
    fifo = deque()
    reads, sets = [], []
    for e in rows:
        check(
            1 <= e.kind <= PACK_READ and e.reserved == 0 and 0 <= e.begin <= e.ns and e.ns > 0,
            "invalid record",
        )
        if e.kind not in (11, 12, 13, 14, READ, SET, PUBLISH, FAIL, 28, PACK_READ):
            continue
        key = identity(e)
        place = e.layer, e.slot
        site = e.call, e.tile, e.wave
        if e.kind == 11:
            check(key not in reserved and place in slots and e.layer == 0, "reservation")
            prior_expert, prior_gen = slots[place]
            check(e.a == prior_expert and e.gen == prior_gen + 1, "slot generation")
            check(site[:2] == (1, 2 if e.expert == 4 else 1), "reservation origin")
            slots[place] = (e.expert, e.gen)
            reserved[key] = site
        elif e.kind == 12:
            check(key in reserved and site == reserved[key], "enqueue origin")
            fifo.append(key)
        elif e.kind in (13, 14, 28):
            check(fifo and key == fifo.popleft(), "FIFO identity")
            check(e.kind == 13, "unexpected skip/cancel in cold fixture")
            check(
                e.worker in range(4) and key not in claimed and e.worker not in live,
                "worker already claimed",
            )
            check(site == reserved[key], "dispatch origin")
            live[e.worker] = key
            claimed[key] = e.worker
            jobs[key] = [e]
        else:
            check(live.get(e.worker) == key and claimed[key] == e.worker, "unclaimed service")
            check(site == reserved[key] and slots[place] == (e.expert, e.gen), "stale service")
            jobs[key].append(e)
            if e.kind in (PUBLISH, FAIL):
                r, s = check_job(
                    jobs[key], packed=packed, short=short, files=files, weights=weights
                )
                reads.extend(r)
                sets.extend(s)
                del live[e.worker]
    expected = {5} if short else set(range(5))
    check(not live and not fifo and set(reserved) == set(claimed) == set(jobs), "unfinished work")
    check(len(jobs) == len(expected) and {k[3] for k in jobs} == expected, "expected routed jobs")
    interrupts = [e.expert for e in reads if e.c == -1]
    check(interrupts == ([0] if packed and not short else []), "controlled EINTR")
    spans = [(e.begin, e.ns) for e in [*reads, *sets]]
    return {
        "generations": len(jobs),
        "published": kinds[PUBLISH],
        "failed": kinds[FAIL],
        "workers_exited": len(exits),
        "attempts": len(reads),
        "interrupted": len(interrupts),
        "requested_bytes_including_retries": sum(e.b for e in reads),
        "returned_bytes": sum(max(e.c, 0) for e in reads),
        "copies": len(sets),
        "copied_bytes": sum(e.a for e in sets),
        "service_worker_ns": sum(end - start for start, end in spans),
        "service_wall_union_ns": union_ns(spans),
    }


def inspect_journal(path, *, packed, short=False):
    rows, header = read_journal(path)
    return header | reconcile(rows, packed=packed, short=short)


def inspect_family(directory):
    """Join independent native syscall/slot evidence with all three instrumented traces."""
    result = {}
    arms = ("gguf-off", "gguf-on", "pack-off", "pack-on", "pack-short-on")
    comparable = (
        "attempts",
        "requested",
        "returned",
        "kernel_reads",
        "eintr",
        "short_injected",
        "native_calls",
        "native_tiles",
        "native_slots",
        "checked_jobs",
        "validated_matrix_bytes",
        "store_loads",
        "load_failed",
    )
    native = {}
    for arm in arms:
        base = directory / arm
        row = json.loads((base / "native.json").read_bytes())
        packed, short = arm.startswith("pack"), arm == "pack-short-on"
        check(
            row["status"] == "PASS_PACK_NATIVE_CASE"
            and row["short"] is short
            and row["transport"] == ("pack" if packed else "gguf"),
            "native arm identity",
        )
        check(
            row["native_calls"] == 1
            and row["native_tiles"] == ([1] if short else [1, 1])
            and row["joined_workers"] == 4,
            "native drive",
        )
        native[arm] = row
        journal = base / "journal.bin"
        if arm.endswith("off"):
            check(not journal.exists(), "OFF journal")
            continue
        rows, header = read_journal(journal)
        evidence = reconcile(rows, packed=packed, short=short)
        for kind, label in [(7, "gguf")] + ([(PACK_FILE, "pack")] if packed else []):
            event = next(e for e in rows if e.kind == kind)
            stat = row[label + "_stat"]
            check(
                (event.a, event.b, event.fd) == (stat["dev"], stat["ino"], row[label + "_fd"]),
                "native FD and inode",
            )
        check(
            (
                evidence["attempts"],
                evidence["interrupted"],
                evidence["requested_bytes_including_retries"],
                evidence["returned_bytes"],
            )
            == (row["attempts"], row["eintr"], row["requested"], row["returned"]),
            "independent syscall ledger",
        )
        check(
            evidence["attempts"] - evidence["interrupted"] == row["kernel_reads"]
            and row["short_injected"] == int(short),
            "actual kernel calls",
        )
        check(evidence["copied_bytes"] == row["validated_matrix_bytes"], "matrix contents")
        check(
            row["store_loads"] == (evidence["published"] if packed else 0)
            and row["load_failed"] == short,
            "native validity",
        )
        result[arm] = header | evidence
    for transport in ("pack", "gguf"):
        off, on = native[transport + "-off"], native[transport + "-on"]
        check(all(off[name] == on[name] for name in comparable), "observer changed native work")
    check(
        native["pack-on"]["native_slots"] == native["gguf-on"]["native_slots"],
        "transport changed routed slots",
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=["family", "pack-on", "gguf-on", "pack-short-on"])
    parser.add_argument("journal", type=Path)
    args = parser.parse_args()
    result = (
        inspect_family(args.journal)
        if args.arm == "family"
        else inspect_journal(
            args.journal, packed=args.arm != "gguf-on", short=args.arm == "pack-short-on"
        )
    )
    print(json.dumps(result, indent=2, sort_keys=True))
