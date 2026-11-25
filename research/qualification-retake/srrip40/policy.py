"""Two-bit SRRIP and LRU with physical-slot ties and simultaneous demand-wave pins."""

from collections import Counter


class Pool:
    def __init__(self, slots, policy):
        slots = list(slots)
        if policy not in ("srrip", "lru"):
            raise ValueError("unknown replacement policy")
        if len(slots) != 40 or any(type(e) is not int or not -1 <= e < 128 for e in slots):
            raise ValueError("expected 40 physical slots containing expert IDs or -1")
        self._index = {expert: i for i, expert in enumerate(slots) if expert >= 0}
        if len(self._index) != 40 - slots.count(-1):
            raise ValueError("duplicate occupied expert")
        self._slots = slots
        self.policy = policy
        # Occupied entries begin with identical unknown history at P for each rule.
        self._priority = [2 if policy == "srrip" else 0] * 40
        self._clock = 0

    @property
    def slots(self):
        return self._slots.copy()

    def _victim(self, pins):
        if -1 in self._slots:
            return self._slots.index(-1)
        eligible = [i for i, e in enumerate(self._slots) if e not in pins]
        if self.policy == "lru":
            return min(eligible, key=lambda i: (self._priority[i], i))
        while True:
            for i in eligible:
                if self._priority[i] == 3:
                    return i
            # When no eligible RRPV is 3, one increment is sufficient to keep every value in range.
            for i in eligible:
                self._priority[i] += 1

    def serve(self, ranks):
        ranks = tuple(ranks)
        if any(type(expert) is not int or not 0 <= expert < 128 for expert in ranks):
            raise ValueError("invalid routed expert")
        demand = tuple(dict.fromkeys(ranks))
        if len(demand) > 40:
            raise ValueError("simultaneous wave exceeds 40 slots")
        pins = set(demand)
        misses = [e for e in demand if e not in self._index]
        hits = pins.intersection(self._index)
        evictions = 0
        for expert in misses:
            slot = self._victim(pins)
            previous = self._slots[slot]
            if previous >= 0:
                del self._index[previous]
                evictions += 1
            self._slots[slot] = expert
            self._index[expert] = slot
            if self.policy == "srrip":
                self._priority[slot] = 2
        if self.policy == "srrip":
            # A repeated rank in the admission wave is still the same miss.
            for expert in hits:
                self._priority[self._index[expert]] = 0
        else:
            for expert in demand:
                self._clock += 1
                self._priority[self._index[expert]] = self._clock
        return Counter(
            misses=len(misses),
            hits=len(hits),
            evictions=evictions,
            distinct_demands=len(demand),
            rank_uses=len(ranks),
            waves=int(bool(demand)),
            parking_only_waves=int(not demand),
        )
