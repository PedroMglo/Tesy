from __future__ import annotations

from collections import OrderedDict
from collections.abc import Hashable
from dataclasses import dataclass

from tesy.trace import RouteEvent


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    evicted_bytes: int = 0


class ByteLRU:
    def __init__(self, capacity_bytes: int):
        if isinstance(capacity_bytes, bool) or capacity_bytes < 0:
            raise ValueError("capacity_bytes must be non-negative")
        self.capacity_bytes = capacity_bytes
        self.used_bytes = 0
        self._items: OrderedDict[Hashable, int] = OrderedDict()
        self.stats = CacheStats()

    def contains(self, key: Hashable) -> bool:
        return key in self._items

    def touch(self, key: Hashable) -> bool:
        if key not in self._items:
            self.stats.misses += 1
            return False
        self._items.move_to_end(key)
        self.stats.hits += 1
        return True

    def put(self, key: Hashable, size_bytes: int) -> None:
        if size_bytes <= 0:
            raise ValueError("size_bytes must be positive")
        if key in self._items:
            old = self._items.pop(key)
            self.used_bytes -= old
        if size_bytes > self.capacity_bytes:
            return
        while self.used_bytes + size_bytes > self.capacity_bytes and self._items:
            _, evicted = self._items.popitem(last=False)
            self.used_bytes -= evicted
            self.stats.evictions += 1
            self.stats.evicted_bytes += evicted
        self._items[key] = size_bytes
        self.used_bytes += size_bytes


def simulate_demand_lru(
    events: list[RouteEvent],
    ram_cache_bytes: int,
    vram_cache_bytes: int,
    phase: str = "decode",
) -> dict[str, object]:
    ram = ByteLRU(ram_cache_bytes)
    vram = ByteLRU(vram_cache_bytes)
    nvme_to_ram = 0
    ram_to_vram = 0
    demand_uses = 0
    token_ids: set[int] = set()

    for event in events:
        if event.phase != phase:
            continue
        token_ids.add(event.token)
        for use in event.experts:
            demand_uses += 1
            if vram.touch(use.key):
                continue

            if not ram.touch(use.key):
                nvme_to_ram += use.encoded_bytes
                ram.put(use.key, use.encoded_bytes)

            ram_to_vram += use.encoded_bytes
            vram.put(use.key, use.encoded_bytes)

    committed_tokens = len(token_ids)
    if committed_tokens == 0:
        raise ValueError(f"trace has no {phase} tokens")

    return {
        "schema": "tesy.cache_simulation.v1",
        "classification": "SIMULATED",
        "policy": "DEMAND_ONLY_LRU_GPU_EXECUTION",
        "phase": phase,
        "committed_tokens_proxy": committed_tokens,
        "expert_uses": demand_uses,
        "ram_capacity_bytes": ram_cache_bytes,
        "vram_capacity_bytes": vram_cache_bytes,
        "nvme_to_ram_expert_bytes": nvme_to_ram,
        "ram_to_vram_expert_bytes": ram_to_vram,
        "cebct_nvme_bytes_per_token": nvme_to_ram / committed_tokens,
        "cebct_pcie_bytes_per_token": ram_to_vram / committed_tokens,
        "ram_cache": {
            "hits": ram.stats.hits,
            "misses": ram.stats.misses,
            "evictions": ram.stats.evictions,
            "evicted_bytes": ram.stats.evicted_bytes,
            "final_used_bytes": ram.used_bytes,
        },
        "vram_cache": {
            "hits": vram.stats.hits,
            "misses": vram.stats.misses,
            "evictions": vram.stats.evictions,
            "evicted_bytes": vram.stats.evicted_bytes,
            "final_used_bytes": vram.used_bytes,
        },
        "claim_boundary": (
            "Trace replay only. Transfer bytes are simulated encoded expert bytes, "
            "not measured NVMe, DRAM or PCIe traffic."
        ),
    }
