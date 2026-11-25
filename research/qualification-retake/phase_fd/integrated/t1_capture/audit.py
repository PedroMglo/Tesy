"""Conserve the PFJ1 suffix of T1 and independently compare the complete nominal T2."""

import hashlib
import importlib.util
import json
from collections import Counter, OrderedDict, deque
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "analyse.py"
PIN = "28c224bd734f841fb87a9e3b1350f0a1008308898d2629a396c7b21d2a56b443"
PRIOR = "1a96cca8af0fd2dd0a4e4fd1ba2afc031320e6ff0be9b335cead5f5e0035f018"
PAYLOAD = 13_219_200
CAPS = (239, 353)
spec = importlib.util.spec_from_file_location("t1_capture_pfj1", SOURCE)
fd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fd)
check = fd.check


def digest(value):
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def record_digest(rows, sealed=False):
    h = hashlib.sha256()
    if sealed:
        h.update(fd.HEADER.pack(b"TESYPF1\0", 1, 96, 262144, len(rows), len(rows), 1, 0))
    for row in rows:
        h.update(fd.RECORD.pack(*row))
    return h.hexdigest()


def conservation(rows, header, model, masked):
    # Keep the original historical executable available at its original SHA for
    # existing receipts. Its default infers the 5-token mask only for standalone
    # T2. All original validation is reused; specialise that one expression.
    source = SOURCE.read_bytes()
    check(hashlib.sha256(source).hexdigest() == PIN, "PFJ1 auditor pin")
    clause = "not (nominal and number == 1)"
    check(source.count(clause.encode()) == 1 and type(masked) is int, "mask specialization")
    namespace = {"__name__": "t1_capture_pfj1_mask", "masked": masked}
    exec(
        compile(source.decode().replace(clause, "number != masked"), str(SOURCE), "exec"), namespace
    )
    return namespace["_audit"](rows, header, model)


def key_tier(key):
    return "cpu" if key[0] < 25 else "cuda"


def per_tier(keys):
    counts = Counter(map(key_tier, keys))
    return {tier: counts[tier] for tier in ("cpu", "cuda")}


def state_before(rows):
    """Return primary descriptor/claim vectors, its FIFO and READY victims in occurrence order."""
    initial = [r for r in rows if r.kind == 5]
    slots = {(r.layer, r.slot): (r.expert, r.gen, r.a, r.b) for r in initial}
    check(len(initial) == len(slots) == 1440, "primary snapshot count")
    for (layer, slot), (expert, gen, state, claim) in slots.items():
        check(0 <= layer < 36 and 0 <= slot < 40 and gen >= 0, "primary index")
        check(state in (0, 1, 2) and claim in (0, 1) and (not claim or state == 1), "primary state")
        check((expert == -1 and state == 0) or (state != 0 and 0 <= expert < 128), "primary expert")
    fifo = deque(fd.identity(r) for r in rows if r.kind == 6 and r.b == 1)
    victims = []
    for r in rows:
        if r.kind not in (11, 12, 13, 14, 17, 28):
            continue
        site = (r.layer, r.slot)
        old, gen, state, claim = slots[site]
        if r.kind == 11:
            check(
                state in (0, 2) and not claim and old == r.a and gen + 1 == r.gen,
                "victim generation",
            )
            if state == 2:
                victims.append((r.layer, old))
            slots[site] = (r.expert, r.gen, 1, 0)
        elif r.kind == 12:
            fifo.append(fd.identity(r))
        elif r.kind in (13, 14, 28):
            check(fifo and fifo.popleft() == fd.identity(r), "primary FIFO")
            if r.kind == 13:
                check((old, gen, state, claim) == (r.expert, r.gen, 1, 0), "primary claim")
                slots[site] = (old, gen, 1, 1)
        else:
            check((old, gen, state, claim) == (r.expert, r.gen, 1, 1), "READY publication")
            slots[site] = (old, gen, 2, 0)
    return [slots[layer, slot] for layer in range(36) for slot in range(40)], list(fifo), victims


def lru(victims, capacity):
    order = OrderedDict()
    first = OrderedDict()
    copies = Counter()
    for key in victims:
        if len(first) < capacity:
            first[key] = None
        if key in order:
            order.move_to_end(key)
        else:
            if len(order) == capacity:
                order.popitem(last=False)
            order[key] = None
            copies[key_tier(key)] += 1
    cold = {tier: copies[tier] for tier in ("cpu", "cuda")}
    initial_credit = per_tier(first)
    low = {tier: n - initial_credit[tier] for tier, n in cold.items()}
    keys = list(map(list, order))
    return {
        "identified": len(first) == capacity,
        "capacity": capacity,
        "ordered_keys": keys,
        "ordered_keys_sha256": digest(keys),
        "retained_by_tier": per_tier(order),
        "cold_start_copies_by_tier": cold,
        "minimum_copies_over_unknown_start_by_tier": low,
        "cold_start_copy_bytes_by_tier": {tier: n * PAYLOAD for tier, n in cold.items()},
        "minimum_copy_bytes_over_unknown_start_by_tier": {
            tier: n * PAYLOAD for tier, n in low.items()
        },
    }


def capture_prefix(rows):
    """Use exclusively immutable records already visible before the second POST."""
    enters = [r for r in rows if r.kind == 1]
    returns = [r for r in rows if r.kind == 2]
    check(
        enters and [r.call for r in enters] == list(range(1, len(enters) + 1)), "T1 call sequence"
    )
    check([r.call for r in returns] == [r.call for r in enters], "T1 incomplete return")
    check(all(r.a == 1 and r.b == r.c for r in enters), "T1 must contain only unit decode")
    positions = [r.b for r in enters]
    check(
        2043 <= positions[0] <= 2119 and positions == list(range(positions[0], 2120)),
        "T1 position coverage",
    )
    slots, fifo, victims = state_before(rows)
    return {
        "t1_calls": len(enters),
        "first_position": positions[0],
        "last_position": positions[-1],
        "t1_last_return_ns": returns[-1].ns,
        "slots_at_t2_sha256": digest(slots),
        "queued_at_t2_sha256": digest(fifo),
        "victim_offers": len(victims),
        "victim_offers_by_tier": per_tier(victims),
        "distinct_victim_keys": len(set(victims)),
        "capacities": {str(k): lru(victims, k) for k in CAPS},
    }


def authority_projection(rows, start_call):
    # Track deterministic host actions separately from worker completion order.
    host = []
    dispatch = []
    service = []
    publication = []
    for r in rows:
        kind = r.kind
        if r.call < start_call:
            continue
        site = (kind, r.call - start_call + 1, r.tile, r.layer, r.wave)
        binding = (r.expert, r.slot, r.gen)
        if kind in (1, 3):
            host.append((*site, r.a, r.b, r.c))
        elif kind in (4, 9, 23, 27):
            host.append((*site, r.a, r.b))
        elif kind in (10, 11, 12):
            host.append((*site, *binding, r.a))
        if kind in (13, 14, 28):
            dispatch.append((*site, *binding))
        if kind in (11, 13, 17):
            service.append((*site, *binding))
        if kind == 17:
            publication.append((*site, *binding))
    return {"host": host, "dispatch": dispatch, "service": service, "publication": publication}


def compare_projections(current, prior):
    result = {}
    for field in ("host", "dispatch", "service", "publication"):
        equal = current[field] == prior[field]
        result[field] = {
            "equal": equal,
            "current": digest(current[field]),
            "prior": digest(prior[field]),
            "count_current": len(current[field]),
            "count_prior": len(prior[field]),
        }
        if field in ("host", "dispatch"):
            check(equal, "T2 " + field + " route/order/binding")
    return result


def audit(rows, header, prior_rows, model: Path, seal):
    count = seal["records"]
    check(type(count) is int and 0 < count < len(rows), "prefix count")
    prefix = rows[:count]
    tail = rows[count:]
    check(
        seal["bytes"] == count * fd.RECORD.size and record_digest(prefix) == seal["sha256"],
        "pre-POST digest",
    )
    check(record_digest(prior_rows, sealed=True) == PRIOR, "prior T2 sealed journal")
    check(record_digest(rows, sealed=True) == header["journal_sha256"], "current journal digest")
    check(tail[0].kind == 1 and tail[0].a == 5, "first post-seal record")
    chosen = capture_prefix(prefix)
    shift = chosen["t1_calls"]
    check(tail[0].call == shift + 1, "noncontiguous T1/T2 call boundary")
    check(all(r.kind != 5 for r in tail), "unexpected second manager snapshot")

    def weights(records):
        return {(r.layer, r.component): (r.a, r.b) for r in records if r.kind == 8}

    sizes = weights(rows)
    check(len(sizes) == 108 and sizes == weights(prior_rows), "GGUF role offsets/sizes")
    check(all(width == PAYLOAD // 3 for _, width in sizes.values()), "materialization bytes")
    check(model is not None, "missing model inode identity")
    result = conservation(rows, header, model, shift + 1)
    old = fd._audit(prior_rows, {"records": len(prior_rows), "flags": 1}, model)
    expected = [(5, [2044, 2048], [5]), (148, [2049, 2196], [32, 32, 32, 32, 20])]
    expected += [(1, [p, p], [1]) for p in range(2197, 2243)]

    def geometry(calls):
        return [(c["tokens"], c["positions"], c["tiles"]) for c in calls]

    check(
        geometry(old["calls"]) == geometry(result["calls"][shift:]) == expected,
        "T2 positions/tiles",
    )
    check(all(c["tiles"] == [1] for c in result["calls"][:shift]), "T1 graph geometry")
    # FILE/SLOT/WEIGHT/initial queue precede the first TILE, under the same manager lock.
    # Ignore any early inherited asynchronous component completions for the snapshot comparison.
    initial = [r for r in prior_rows if r.kind == 5 or (r.kind == 6 and r.b == 1)]
    slots, fifo, _ = state_before(initial)
    check(chosen["slots_at_t2_sha256"] == digest(slots), "T2 primary slots/claims/generations")
    check(chosen["queued_at_t2_sha256"] == digest(fifo), "T2 primary queue")
    parts = compare_projections(
        authority_projection(tail, shift + 1), authority_projection(prior_rows, 1)
    )
    return {
        "status": "PASS",
        "prefix": chosen,
        "structure": {
            "t1_calls": shift,
            "t2_calls": len(expected),
            "first_decode_checked": True,
            "last_position_checked": 2242,
            "first_t2_record": count,
            "positions": [[2044, 2048], [2049, 2196], [2197, 2242]],
            "slots_at_t2_sha256": chosen["slots_at_t2_sha256"],
            "queue_at_t2_sha256": chosen["queued_at_t2_sha256"],
            "t2_signature_sha256": parts["host"]["current"],
            "service_interleaving_equal": parts["service"]["equal"],
            "projections": parts,
            "prior_journal_sha256": PRIOR,
            "journal_sha256": header["journal_sha256"],
            "full_conservation": result["event_counts"],
            "prior_conservation": old["event_counts"],
            "census_fd_checked": result["fd_identity_checked"] and old["fd_identity_checked"],
        },
    }
