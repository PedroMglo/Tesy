"""Transport bounds with explicit epistemic status; no measured-rate hard cap."""
from __future__ import annotations
from fractions import Fraction
from typing import Any
from .io import integer, keys, require


def transport_bound(raw: Any) -> dict:
    keys(raw, {'schema', 'minimum_tokens_per_second', 'tiers'}, 'roofline')
    require(raw['schema'] == 'tesy.roofline.v1', 'roofline schema differs')
    q = raw['minimum_tokens_per_second']
    keys(q, {'numerator', 'denominator'}, 'threshold')
    minimum = Fraction(integer(q['numerator'], 'threshold numerator', 1),
                       integer(q['denominator'], 'threshold denominator', 1))
    require(type(raw['tiers']) is list and 1 <= len(raw['tiers']) <= 8, 'invalid tiers')
    rows, hard, estimated, unknown, names = [], False, False, False, set()
    for tier in raw['tiers']:
        keys(tier, {'name', 'bytes_per_committed_token', 'bandwidth_Bps', 'bandwidth_kind'}, 'tier')
        name = tier['name']
        require(name in ('nvme', 'h2d', 'd2h', 'dram') and name not in names, 'duplicate/invalid tier')
        names.add(name)
        n = integer(tier['bytes_per_committed_token'], 'bytes/token')
        kind, bandwidth = tier['bandwidth_kind'], tier['bandwidth_Bps']
        require(kind in ('UPPER_BOUND', 'MEASURED_REFERENCE', 'ASSUMED', 'UNKNOWN'), 'bandwidth kind')
        if kind == 'UNKNOWN':
            require(bandwidth is None, 'unknown bandwidth must be null')
            unknown |= n > 0
            rows.append({'name': name, 'time_floor_seconds': None})
            continue
        bandwidth = integer(bandwidth, 'bandwidth', 1)
        floor = Fraction(n, bandwidth)
        violates = floor > 1 / minimum
        hard |= violates and kind == 'UPPER_BOUND'
        estimated |= violates and kind != 'UPPER_BOUND'
        rows.append({'name': name, 'time_floor_seconds': {'numerator': floor.numerator,
                                                         'denominator': floor.denominator},
                     'classification': kind, 'threshold_exceeded': violates})
    decision = ('NOGO_HARD_TRANSPORT_BOUND' if hard else 'ESTIMATED_INFEASIBLE' if estimated
                else 'INCONCLUSIVE_MISSING_BANDWIDTH' if unknown else 'NOT_EXCLUDED_BY_TRANSPORT')
    return {'schema': 'tesy.roofline-result.v1', 'classification': 'DERIVED_STATIC',
            'decision': decision, 'tiers': rows, 'qualification': False,
            'warning': 'Per-tier bounds only. No free overlap, compute model, or speedup established.'}
