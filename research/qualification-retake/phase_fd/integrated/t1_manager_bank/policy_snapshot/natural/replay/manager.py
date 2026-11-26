"""Source-level C269 slot decisions. No modeling of latency or worker completion order."""

from collections import Counter
from dataclasses import dataclass, field
from hashlib import sha256

CAP = 18
RANKS = 4
SLOTS = 40
PAYLOAD = 13_219_200
PACK = 13_221_888


def require(ok, message):
    if not ok:
        raise ValueError(message)


class OrderUnknown(Exception):
    """The overlap can change the set of eligible victims at a reservation."""


@dataclass
class Pool:
    ids: list
    gen: list
    ages: list
    heat: list
    clock: int
    parking: list = field(default_factory=list)
    possible_loading: set = field(default_factory=set)
    plan: list = field(default_factory=list)
    next_wave: int = 0
    next_count: int = 0


def victim(p, keep, bank):
    available = [s for s in range(SLOTS) if s not in keep]
    empty = [s for s in available if p.ids[s] == -1]
    if empty:
        return empty[0]
    if not available:
        raise OrderUnknown("all slots kept / could wait for a worker")
    tagged = [s for s in available if p.ids[s] in bank]
    choices = tagged or available
    return min(choices, key=lambda s: (p.heat[p.ids[s]], p.ages[s], s))


def touch(p, slot):
    p.clock += 1
    p.ages[slot] = p.clock


class Manager:
    def __init__(self, slots, words, calls, interval, bank):
        self.pools = []
        self.calls = calls
        self.interval = interval
        self.bank = bank
        self.proofs = Counter()
        self.emitted = sha256()
        require(len(words) == 36 and len(slots) == 1440 and interval == 2304, "manager geometry")
        for layer, row in enumerate(words):
            state = slots[layer * SLOTS : (layer + 1) * SLOTS]
            ids = [x[0] for x in state]
            valid = [i for i in ids if i != -1]
            require(
                len(row) == 169
                and all(0 <= h <= 2**32 - 2 for h in row[41:])
                and all(0 <= age <= row[0] for age in row[1:41])
                and all((x[2], x[3]) == (2 if x[0] >= 0 else 0, 0) and x[1] >= 0 for x in state)
                and len(set(valid)) == len(valid)
                and all(0 <= i < 128 for i in valid),
                "invalid initial policy words or undrained pool",
            )
            self.pools.append(
                Pool(ids, [x[1] for x in state], list(row[1:41]), list(row[41:]), row[0])
            )

    def callback(self, layer, wave, ranks):
        p = self.pools[layer]
        unique = list(dict.fromkeys(ranks))
        require(len(ranks) % RANKS == 0 and len(unique) >= RANKS, "rank geometry")
        ranks_count = len(ranks)
        multi = min(ranks_count, 128) > SLOTS
        if wave in (-1, 0):
            require(
                (wave == 0) == multi and p.next_wave == p.next_count, "remap shape or lost waves"
            )
            self.calls += 1
            if wave == -1:
                for e in unique:
                    p.heat[e] = min(2**32 - 2, p.heat[e] + 1)
                if self.calls % self.interval == 0:
                    self.proofs["whole_manager_decays"] += 1
                    for pool in self.pools:
                        pool.heat = [h >> 1 for h in pool.heat]
            else:
                p.plan = unique
                p.next_wave = 0
                p.next_count = (min(ranks_count, 128) + CAP - 1) // CAP
        if wave == -1:
            current, following = unique, []
        else:
            require(multi and wave == p.next_wave and p.plan == unique, "wave progression")
            p.next_wave += 1
            current = unique[wave * CAP : (wave + 1) * CAP]
            following = unique[(wave + 1) * CAP : (wave + 2) * CAP]
        # The previous barrier waited for all its own demands. Of this layer only
        # its next-wave reads might still be loading; other layers cannot consume its slots.
        if not p.possible_loading.issubset(current) or (
            p.possible_loading and not set(current).issubset(p.ids)
        ):
            raise OrderUnknown(
                "foreign loading or current misses before protecting outstanding loads"
            )
        if p.possible_loading:
            self.proofs["callbacks_with_potential_unfinished_preloads"] += 1
        borrowed = p.parking[: max(0, RANKS - len(current))] if multi else []
        require(len(borrowed) == (max(0, RANKS - len(current)) if multi else 0), "parking history")
        keep = set(borrowed)
        keep.update(s for s, e in enumerate(p.ids) if e in following)
        allocations, demands, new_loading = [], [], set()

        def ensure(e, reason):
            if e in p.ids:
                return p.ids.index(e)
            # During this planning interval new reads might complete eventually, but
            # all slots they could occupy are already in keep at every later decision.
            if any(p.ids.index(i) not in keep for i in p.possible_loading | new_loading):
                raise OrderUnknown("could select an unfinished slot")
            slot = victim(p, keep, self.bank[layer])
            old = p.ids[slot]
            p.gen[slot] += 1
            p.ids[slot] = e
            touch(p, slot)
            allocations.append((e, slot, p.gen[slot], old, reason))
            new_loading.add(e)
            return slot

        for e in current:
            s = ensure(e, 0)
            keep.add(s)
            demands.append((e, s, p.gen[s]))
        potential_next = set()
        for e in following:
            if e not in p.ids:
                s = ensure(e, 2)
                keep.add(s)
                potential_next.add(e)
        require(set(current + following).issubset(p.ids), "next wave preload missing")
        p.possible_loading = potential_next
        if multi:
            p.parking = [s for _, s, _ in demands] + borrowed
            require(
                len(set(p.parking)) == len(p.parking) and len(p.parking) >= RANKS, "invalid parking"
            )
        indexes = {e: s for e, s, _ in demands}
        for start in range(0, len(ranks), RANKS):
            batch = ranks[start : start + RANKS]
            row = [indexes.get(e, -1) for e in batch]
            used = set(s for s in row if s >= 0)
            for s in row:
                if s >= 0:
                    touch(p, s)
            if multi:
                parks = iter(s for s in p.parking if s not in used)
                for k, s in enumerate(row):
                    if s >= 0:
                        continue
                    parked = next(parks)
                    require(
                        p.ids[parked] >= 0 and p.ids[parked] not in potential_next,
                        "parking pending",
                    )
                    if layer < 25:
                        self.proofs["masked_cpu_sentinels"] += 1
                    else:
                        self.proofs["masked_cuda_parking_ranks"] += 1
                    row[k] = -1 if layer < 25 else parked
            self.emitted.update(bytes(s + 1 for s in row))
        return allocations, demands


def repair(src, ref, bank, bases, counts):
    """Price the identities absent/moved at the physical cut; no unsafe generation rewind."""
    detail = Counter()
    for layer, (p, r) in enumerate(zip(src.pools, ref.pools, strict=True)):
        require(not p.possible_loading and not r.possible_loading, "undrained decode cut")
        edges = {}
        detail["removed_members"] += len(set(p.ids) - set(r.ids) - {-1})
        detail["different_heat_words"] += sum(a != b for a, b in zip(p.heat, r.heat, strict=True))
        detail["different_layer_clocks"] += int(p.clock != r.clock)
        for s, wanted in enumerate(r.ids):
            if wanted >= 0 and wanted not in p.ids:
                charge(counts, layer, wanted, bank, bases)
                detail["missing_members"] += 1
            elif wanted >= 0 and wanted != p.ids[s]:
                edges[p.ids.index(wanted)] = s
                detail[
                    "same_tier_slot_moves_cpu" if layer < 25 else "same_tier_slot_moves_cuda"
                ] += 1
            if wanted != p.ids[s]:
                detail["different_bindings"] += 1
            if r.gen[s] != p.gen[s]:
                detail["different_generation_words"] += 1
            if r.ages[s] != p.ages[s]:
                detail["different_age_words"] += 1
        while edges:
            visited = set()
            first = next(iter(edges))
            while first in edges:
                visited.add(first)
                first = edges.pop(first)
            if first in visited:
                detail["cycles"] += 1
    for tier in ("cpu", "cuda"):
        detail["slot_move_payload_bytes_" + tier] = detail["same_tier_slot_moves_" + tier] * PAYLOAD
    return dict(detail)


def charge(counts, layer, e, bank, bases):
    tier = "cpu" if layer < 25 else "cuda"
    c = counts[tier]
    c["admissions"] += 1
    c["primary_bytes"] += PAYLOAD
    c["host_to_primary_" + tier + "_bytes"] += PAYLOAD
    if e in bank[layer]:
        c["bank_hits"] += 1
        c["host_bank_delivered_bytes"] += PAYLOAD
    else:
        c["disk_jobs"] += 1
        c["gguf_pread_bytes"] += sum(
            (((base + size * e) % 4096 + size + 4095) // 4096) * 4096 for base, size in bases[layer]
        )
        c["packed_pread_bytes"] += PACK


def totals(counts):
    return {tier: dict(c) for tier, c in {**counts, "all": counts["cpu"] + counts["cuda"]}.items()}
