"""Streaming shadow banks. Each admission needs an actual, live victim offer."""

from collections import Counter


class VictimBank:
    def __init__(self, capacity, use_prefill):
        if capacity <= 0:
            raise ValueError("capacity")
        self.capacity = capacity
        self.use_prefill = use_prefill
        self.frequency = Counter()
        self.held = {}
        self.admissions = Counter()
        self.offers = 0
        self.rejected = 0
        self.repeated = 0
        self.evictions = 0

    def rank_row(self, layer, ids):
        if len(ids) != 4 or len(set(ids)) != 4 or any(e not in range(128) for e in ids):
            raise ValueError("top-4")
        if self.use_prefill:
            self.frequency.update((layer, e) for e in ids)

    def priority(self, key):
        return self.frequency[key], self.held[key], key

    def offer(self, key):
        self.offers += 1
        if key in self.held:
            self.held[key] = self.offers
            self.repeated += 1
            return
        self.held[key] = self.offers
        if len(self.held) > self.capacity:
            drop = min(self.held, key=self.priority)
            del self.held[drop]
            if drop == key:
                self.rejected += 1
                return
            self.evictions += 1
        self.admissions["CPU" if key[0] < 25 else "CUDA0"] += 1

    def receipt(self):
        admitted = sum(self.admissions.values())
        if (
            self.offers != admitted + self.repeated + self.rejected
            or len(self.held) != admitted - self.evictions
        ):
            raise ValueError("bank conservation")
        return {
            "offers": self.offers,
            "rejected": self.rejected,
            "repeated": self.repeated,
            "evictions": self.evictions,
            "held": len(self.held),
            "copies": {k: self.admissions[k] for k in ("CPU", "CUDA0")},
        }


def replay(prefix, prefill_calls, capacity=353):
    """Caller first authenticates the byte cut and verifies all T1 position and row populations."""
    banks = {name: VictimBank(capacity, use) for name, use in (("lru", False), ("prefill", True))}
    slots, offered = {}, set()
    for r in prefix:
        key = r.layer, r.slot
        if r.kind == 5:
            if key in slots or r.a not in (0, 2) or r.b:
                raise ValueError("starting slot")
            slots[key] = r.expert, r.gen, r.a
        elif r.kind == 27 and r.call in prefill_calls:
            if not 0 <= r.a < 2**32:
                raise ValueError("rank encoding")
            ids = r.a.to_bytes(4, "little")
            for bank in banks.values():
                bank.rank_row(r.layer, ids)
        elif r.kind == 11:
            old, gen, state = slots[key]
            if old != r.a or gen + 1 != r.gen or state not in (0, 2):
                raise ValueError("victim generation")
            if state == 2:
                victim = r.layer, old
                offered.add(victim)
                for bank in banks.values():
                    bank.offer(victim)
            slots[key] = r.expert, r.gen, 1
        elif r.kind == 17:
            if slots[key] != (r.expert, r.gen, 1):
                raise ValueError("stale publication")
            slots[key] = r.expert, r.gen, 2
        elif r.kind == 18:
            raise ValueError("failed load in T1")
    if len(slots) != 1440 or any(v[2] != 2 for v in slots.values()):
        raise ValueError("T1 final slots")
    for bank in banks.values():
        bank.receipt()
    return banks, offered, slots
