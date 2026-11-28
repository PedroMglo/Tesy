"""CPU frame residency between native target waves. Counts, never wall-clock prices."""

import hashlib
import json
from collections import Counter, deque
from dataclasses import dataclass

LAYERS, EXPERTS, CAPACITY, SCRATCH = 25, 128, 1212, 40
STRIDE = 13_221_888
EQUAL = [49] * 12 + [48] * 13


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(data):
    return hashlib.sha256(json.dumps(data, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Wave:
    call: int
    tile: int
    layer: int
    index: int
    keys: tuple


def waves(visits):
    out = []
    for (call, tile, layer), ranks in visits.items():
        need(ranks and len(ranks) % 4 == 0 and len(ranks) <= 128, "target row count")
        for i in range(0, len(ranks), 4):
            ids = ranks[i : i + 4]
            need(min(ids) >= 0 and max(ids) < 128 and len(set(ids)) == 4, "target top four")
        keys = tuple(layer * EXPERTS + e for e in dict.fromkeys(ranks))
        n = len(ranks)
        if n <= 40:
            out.append(Wave(call, tile, layer, -1, keys))
        else:
            for i in range((n + 17) // 18):
                out.append(Wave(call, tile, layer, i, keys[18 * i : 18 * (i + 1)]))
    return out


def trim(bank, cap):
    while len(bank) > cap:
        del bank[next(iter(bank))]


def update(bank, keys):
    for k in keys:
        bank.pop(k, None)
        bank[k] = None


def layers(initial):
    banks = [{} for _ in range(LAYERS)]
    for k in initial:
        need(0 <= k < LAYERS * EXPERTS and k not in banks[k // EXPERTS], "initial CPU key")
        banks[k // EXPERTS][k] = None
    return banks


def curves(waves, initial):
    """A hit at pre-wave position d (MRU = 1) serves every capacity c >= d."""
    banks, positions = layers(initial), [[0] * (EXPERTS + 1) for _ in range(LAYERS)]
    for w in waves:
        bank = banks[w.layer]
        rank = {k: d for d, k in enumerate(reversed(bank), 1)}
        for k in w.keys:
            if k in rank:
                positions[w.layer][rank[k]] += 1
        update(bank, w.keys)
    for curve in positions:
        for c in range(1, len(curve)):
            curve[c] += curve[c - 1]
    return positions, [list(b) for b in banks]


def allocate(scores, capacity=CAPACITY):
    """Exact integer budget; first maximizer assigns least to the newest layer."""
    best = [0] + [None] * capacity
    choices = []
    for curve in scores:
        next_row = [None] * (capacity + 1)
        choice = [-1] * (capacity + 1)
        for count, value in enumerate(curve[: capacity + 1]):
            for used, prefix in enumerate(best[: capacity + 1 - count]):
                if prefix is None:
                    continue
                at = used + count
                score = prefix + value
                if next_row[at] is None or score > next_row[at]:
                    next_row[at] = score
                    choice[at] = count
        choices.append(choice)
        best = next_row
    need(best[capacity] is not None, "infeasible allocation")
    used, quotas = capacity, []
    for row in reversed(choices):
        q = row[used]
        quotas.append(q)
        used -= q
    need(used == 0, "budget conservation")
    return quotas[::-1], best[capacity]


def local_run(waves, initial, quotas, phase):
    banks = layers(initial)
    need(len(quotas) == len(banks) and sum(quotas) == CAPACITY, "partition budget")
    for bank, cap in zip(banks, quotas, strict=True):
        trim(bank, cap)
    entry = sum(map(len, banks))
    out = Counter()
    for w in waves:
        bank = banks[w.layer]
        out[phase(w.call)] += sum(k not in bank for k in w.keys)
        update(bank, w.keys)
        trim(bank, quotas[w.layer])
    return dict(out), [k for bank in banks for k in bank], entry


def global_run(waves, initial, phase):
    bank = dict.fromkeys(initial)
    trim(bank, CAPACITY)
    entry = len(bank)
    counts = Counter()
    for w in waves:
        counts[phase(w.call)] += sum(k not in bank for k in w.keys)
        update(bank, w.keys)
        trim(bank, CAPACITY)
    return dict(counts), list(bank), entry


def ideal(waves, initial, cap, phase, restore=()):
    """Unit misses with bypass. A virtual terminal demand charges missing restore keys."""
    groups = [(phase(w.call), w.keys) for w in waves]
    if restore:
        groups.append(("restore", tuple(restore)))
    future = {}
    for t, (_, group) in enumerate(groups):
        for k in group:
            future.setdefault(k, deque()).append(t)
    infinity = len(groups)
    bank = set(initial)
    need(len(bank) <= cap, "oracle initial capacity")
    misses = Counter()
    for t, (label, group) in enumerate(groups):
        misses[label] += sum(k not in bank for k in group)
        if label == "restore":
            break
        for k in group:
            need(future[k].popleft() == t, "future index")
        bank.update(group)
        excess = len(bank) - cap
        if excess > 0:

            def priority(k):
                times = future.get(k)
                return (times[0] if times else infinity, k)

            bank.difference_update(sorted(bank, key=priority, reverse=True)[:excess])
    return dict(misses), sorted(bank)


def prove_curve(curves_by_layer, quotas, demands, misses):
    predicted = sum(row[q] for row, q in zip(curves_by_layer, quotas, strict=True))
    need(predicted == demands - sum(misses.values()), "stack curve disagrees with bounded cache")
