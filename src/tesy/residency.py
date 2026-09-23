"""Serial two-cache replay. No compute model, physical I/O or measured speedup.

RAM and GPU are independent, non-inclusive, immutable caches. A GPU hit needs
no RAM copy; GPU eviction has no writeback. On GPU miss: RAM hit or source read
via bounded host staging, then H2D. Oversize RAM objects bypass that cache.
Every expert must fit GPU cache and staging; unsupported placement fails closed.
"""
from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .io import digest, integer, keys, require, text

Expert = tuple[int, int]


@dataclass(frozen=True)
class Event:
    token: int
    layer: int
    experts: tuple[Expert, ...]


@dataclass(frozen=True)
class Trace:
    session: str
    kind: str
    sizes: dict[Expert, int]
    layers: tuple[int, ...]
    events: tuple[Event, ...]


def parse_trace(raw: Any) -> Trace:
    keys(raw, {'schema', 'session_id', 'provenance', 'layers', 'experts', 'events'}, 'trace')
    require(raw['schema'] == 'tesy.routing-trace.v1', 'unsupported trace schema')
    session = text(raw['session_id'], 'session_id')
    provenance = keys(raw['provenance'], {'kind', 'model_sha256', 'route_semantics'}, 'provenance')
    require(provenance['kind'] in ('SYNTHETIC', 'OBSERVED'), 'unknown trace kind')
    require(provenance['route_semantics'] == 'sequential_target',
            'v1 requires sequential target routing, not a speculative tree')
    if provenance['kind'] == 'OBSERVED':
        digest(provenance['model_sha256'])
    else:
        require(provenance['model_sha256'] is None, 'synthetic trace must not impersonate a model')
    layers = raw['layers']
    require(type(layers) is list and 1 <= len(layers) <= 256, 'invalid layers')
    for layer in layers:
        integer(layer, 'layer', 0, 4095)
    require(layers == sorted(set(layers)), 'layers must be unique and ordered')
    require(type(raw['experts']) is list and 1 <= len(raw['experts']) <= 100_000,
            'invalid expert inventory')
    sizes = {}
    for obj in raw['experts']:
        keys(obj, {'layer', 'expert', 'bytes'}, 'expert')
        layer = integer(obj['layer'], 'expert layer', 0, 4095)
        expert = integer(obj['expert'], 'expert id', 0, 1_000_000)
        require(layer in layers and (layer, expert) not in sizes, 'duplicate/unknown expert layer')
        sizes[layer, expert] = integer(obj['bytes'], 'expert bytes', 1)
    events = raw['events']
    require(type(events) is list and 1 <= len(events) <= 100_000, 'invalid events')
    require(len(events) % len(layers) == 0, 'incomplete token/layer group')
    out = []
    first_token = None
    for i, e in enumerate(events):
        keys(e, {'step', 'token', 'layer', 'experts'}, 'event')
        require(integer(e['step'], 'step') == i, 'non-contiguous steps')
        token = integer(e['token'], 'token')
        if first_token is None:
            first_token = token
        require(token == first_token + i // len(layers), 'non-contiguous tokens')
        layer = integer(e['layer'], 'event layer', 0, 4095)
        require(layer == layers[i % len(layers)], 'layer chronology differs')
        ids = e['experts']
        require(type(ids) is list and 1 <= len(ids) <= 256, 'invalid routed experts')
        for expert in ids:
            integer(expert, 'routed expert', 0, 1_000_000)
            require((layer, expert) in sizes, 'unknown routed expert')
        require(len(ids) == len(set(ids)), 'duplicate expert in event')
        out.append(Event(token, layer, tuple((layer, expert) for expert in ids)))
    return Trace(session, provenance['kind'], sizes, tuple(layers), tuple(out))


def profile(raw: Any) -> dict:
    expected = {'schema', 'ram_cache_bytes', 'gpu_cache_bytes', 'staging_bytes',
                'ram_limit_bytes', 'ram_reserve_bytes', 'gpu_limit_bytes',
                'gpu_reserve_bytes', 'bandwidth'}
    keys(raw, expected, 'profile')
    require(raw['schema'] == 'tesy.replay-profile.v1', 'profile schema differs')
    for key in expected - {'schema', 'bandwidth'}:
        integer(raw[key], key)
    require(raw['staging_bytes'] > 0 and raw['gpu_cache_bytes'] > 0, 'zero required capacity')
    require(raw['ram_cache_bytes'] + raw['staging_bytes'] + raw['ram_reserve_bytes']
            <= raw['ram_limit_bytes'], 'RAM budget oversubscribed')
    require(raw['gpu_cache_bytes'] + raw['gpu_reserve_bytes'] <= raw['gpu_limit_bytes'],
            'VRAM budget oversubscribed')
    b = keys(raw['bandwidth'], {'source_Bps', 'h2d_Bps', 'classification'}, 'bandwidth')
    integer(b['source_Bps'], 'source bandwidth', 1)
    integer(b['h2d_Bps'], 'H2D bandwidth', 1)
    require(b['classification'] in ('ASSUMED', 'MEASURED_REFERENCE'), 'bandwidth class differs')
    return raw


class Cache:
    def __init__(self, capacity: int, policy: str):
        self.capacity, self.policy = capacity, policy
        self.entries: OrderedDict[Expert, tuple[int, bool]] = OrderedDict()
        self.frequency: Counter = Counter()
        self.used = self.peak = self.wasted = self.evictions = 0

    def touch(self, expert: Expert, demand: bool = True) -> bool:
        if expert not in self.entries:
            return False
        size, prefetched = self.entries[expert]
        self.entries[expert] = size, prefetched and not demand
        self.entries.move_to_end(expert)
        self.frequency[expert] += 1
        return True

    def put(self, expert: Expert, size: int, prefetched: bool = False) -> None:
        if self.touch(expert, not prefetched):
            return
        if size > self.capacity:
            return  # host cache bypass; the separately budgeted staging owns it.
        while self.used + size > self.capacity:
            victim = (min(self.entries, key=lambda e: self.frequency[e])
                      if self.policy == 'lfu' else next(iter(self.entries)))
            old_size, unused_prefetch = self.entries.pop(victim)
            self.used -= old_size
            self.evictions += 1
            self.wasted += old_size if unused_prefetch else 0
            del self.frequency[victim]
        self.entries[expert] = (size, prefetched)
        self.frequency[expert] = 1
        self.used += size
        self.peak = max(self.peak, self.used)


class Replay:
    """Online policy receives one observed event at a time, no future-event list."""
    def __init__(self, sizes: dict[Expert, int], p: dict, policy: str):
        require(policy in ('lru', 'lfu', 'transition'), 'policy must be lru/lfu/transition')
        self.p, self.sizes, self.policy = profile(p), sizes, policy
        require(max(sizes.values()) <= min(p['staging_bytes'], p['gpu_cache_bytes']),
                'expert exceeds staging/GPU capacity; this replay cannot model that placement')
        self.ram = Cache(p['ram_cache_bytes'], 'lfu' if policy == 'lfu' else 'lru')
        self.gpu = Cache(p['gpu_cache_bytes'], 'lfu' if policy == 'lfu' else 'lru')
        self.stats = Counter(source_request_bytes=0, h2d_payload_bytes=0, demand_requests=0,
                             demand_gpu_hits=0, demand_ram_hits=0, prefetch_requests=0,
                             prefetch_h2d_bytes=0, useful_prefetch_bytes=0)
        self.previous: dict[int, tuple[Expert, ...]] = {}
        self.transitions: dict[tuple[Expert, ...], Counter] = {}
        self.ledger = []

    def fetch(self, expert: Expert, prefetch: bool) -> None:
        size = self.sizes[expert]
        self.stats['prefetch_requests' if prefetch else 'demand_requests'] += 1
        prior = self.gpu.entries.get(expert)
        if self.gpu.touch(expert, not prefetch):
            if not prefetch:
                self.stats['demand_gpu_hits'] += 1
                self.stats['useful_prefetch_bytes'] += size if prior[1] else 0
            return
        if self.ram.touch(expert):
            if not prefetch:
                self.stats['demand_ram_hits'] += 1
        else:
            self.stats['source_request_bytes'] += size
            self.ram.put(expert, size)
        self.stats['h2d_payload_bytes'] += size
        self.stats['prefetch_h2d_bytes'] += size if prefetch else 0
        self.gpu.put(expert, size, prefetch)

    def observe(self, event: Event) -> None:
        for expert in event.experts:
            self.fetch(expert, False)
        if self.policy == 'transition':
            previous = self.previous.get(event.layer)
            if previous is not None:
                self.transitions.setdefault(previous, Counter())[event.experts] += 1
            self.previous[event.layer] = event.experts
            options = self.transitions.get(event.experts)
            if options:
                # Deterministic tie-break and at most one NEW expert per event.
                prediction = min(options, key=lambda key: (-options[key], key))
                for expert in prediction:
                    if expert not in self.gpu.entries:
                        self.fetch(expert, True)
                        break
        self.ledger.append({'token': event.token, 'layer': event.layer,
                            'ram_used': self.ram.used, 'gpu_used': self.gpu.used,
                            'stats': dict(self.stats)})

    def result(self) -> dict:
        b = self.p['bandwidth']
        ns = (Fraction(self.stats['source_request_bytes'] * 10**9, b['source_Bps'])
              + Fraction(self.stats['h2d_payload_bytes'] * 10**9, b['h2d_Bps']))
        unused = sum(size for size, prefetched in self.gpu.entries.values() if prefetched)
        return {'schema': 'tesy.replay-result.v1', 'classification': 'SIMULATED',
                'policy': self.policy, 'stats': dict(self.stats),
                'unused_or_evicted_prefetch_bytes': self.gpu.wasted + unused,
                'ram_peak_bytes': self.ram.peak, 'gpu_peak_bytes': self.gpu.peak,
                'ram_evictions': self.ram.evictions, 'gpu_evictions': self.gpu.evictions,
                'serialized_copy_estimate_ns': {'numerator': ns.numerator,
                                                'denominator': ns.denominator},
                'compute_modelled': False, 'overlap_modelled': False,
                'physical_io_measured': False, 'token_throughput_measured': False,
                'qualification': False, 'ledger': self.ledger}


def replay(trace: Trace, p: dict, policy: str = 'lru') -> dict:
    engine = Replay(trace.sizes, p, policy)
    for event in trace.events:
        engine.observe(event)
    result = engine.result()
    result['session_id'], result['trace_kind'] = trace.session, trace.kind
    result['observed_routing_tokens'] = len(trace.events) // len(trace.layers)
    return result


def union_windows(trace: Trace, k: int) -> dict:
    integer(k, 'window length', 1, 64)
    width = k * len(trace.layers)
    rows = []
    for begin in range(0, len(trace.events), width):
        events = trace.events[begin:begin + width]
        union = set(e for event in events for e in event.experts)
        sequential = sum(trace.sizes[e] for event in events for e in event.experts)
        rows.append({'first_token': events[0].token, 'last_token': events[-1].token,
                     'tokens_in_window': len(events) // len(trace.layers),
                     'distinct_experts': len(union),
                     'encoded_union_bytes': sum(trace.sizes[e] for e in union),
                     'sequential_requested_bytes_without_cache': sequential})
    return {'schema': 'tesy.union-analysis.v1', 'classification': 'OFFLINE_REUSE_POTENTIAL',
            'k': k, 'windows': rows, 'acceptance_measured': False,
            'cold_cache_bytes_measured': False, 'qualification': False,
            'warning': 'Target-only routes omit rejected drafts. No speculative speedup inferred.'}
