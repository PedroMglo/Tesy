"""Offline certificates for earlier same-tier copies into the eventual R0 slots."""

from collections import Counter, defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Eviction:
    seq: int
    tile: int
    layer: int
    slot: int
    old: int
    new: int
    previous_write: int
    ready_since: int | None
    previous_demand: int


def tile_demands(rows):
    tile, previous_layer = -1, 36
    positions = {}
    uses = defaultdict(set)
    for row in rows:
        if row["call_id"] != 2:
            continue
        layer = row["layer"]
        if row["kind"] == "DEMAND":
            if layer < previous_layer:
                if layer != 0:
                    raise ValueError("unknown tile transition")
                tile += 1
            previous_layer = layer
            uses[tile, layer].add(row["expert"])
        positions[row["seq"]] = tile
    if tile != 4:
        raise ValueError("missing C135 call-2 tile")
    return positions, uses


def simultaneous(edges):
    """Each eviction has at most one successor and one predecessor.

    A component is a time-directed path. Taking its first edge is optimal
    for cardinality: it can replace the second edge in any optimal matching.
    Distinct destination-write gaps on one slot have disjoint interiors.
    """
    if (len(set(a for a, _ in edges)) != len(edges)
            or len(set(b for _, b in edges)) != len(edges)
            or any(a >= b for a, b in edges)):
        raise ValueError("expected vertex-disjoint paths before endpoint matching")
    used, chosen = set(), []
    for a, b in sorted(edges):
        if a not in used and b not in used:
            chosen.append((a, b))
            used.update((a, b))
    return chosen


def select(rows):
    tiles, uses = tile_demands(rows)
    writes, ready, demanded = {}, {}, {}
    evicted_expert, replacement, last_slot_eviction = {}, {}, {}
    seen = {}
    eligible, relaxed = [], []
    generations = {}
    counts = Counter()
    for row in rows:
        call = row["call_id"]
        if call > 2:
            break
        kind = row["kind"]
        seq, layer, slot, expert, gen = (row[k] for k in
                                         ("seq", "layer", "slot", "expert", "generation"))
        place = layer, slot
        logical = layer, expert
        tile = tiles.get(seq, -1)
        if kind == "DEMAND":
            demanded[logical] = seq
            if row["state"] == 2:
                ready.setdefault((layer, slot, expert), seq)
                seen[logical] = (call, tile)
        elif kind == "EVICT":
            old = Eviction(seq, tile, layer, slot, expert, row["victim"],
                           writes.get(place, -1), ready.pop((layer, slot, expert), None),
                           demanded.get(logical, -1))
            last_slot_eviction[place] = old
            evicted_expert[logical] = old
        elif kind == "RESERVE":
            writes[place] = seq
        elif kind == "ENQUEUE":
            ev = last_slot_eviction.get(place)
            if ev is not None and ev.new == expert:
                replacement.setdefault((call, layer, slot, gen), ev)
        elif kind == "LOAD_END":
            ready[layer, slot, expert] = seq
        elif kind == "LOAD_BEGIN":
            previous = seen.get(logical)
            seen[logical] = (call, tile)
            if call != 2 or previous is None or previous[0] != 2 or previous[1] == tile:
                continue
            counts["candidates"] += 1
            start = evicted_expert.get(logical)
            end = replacement.get((call, layer, slot, gen))
            if start is None or end is None or start.tile < 0 or end.new != expert:
                raise ValueError("candidate lacks an intra-call eviction identity")
            if start.slot == end.slot or not (end.previous_write < start.seq < end.seq):
                counts["destination_unavailable"] += 1
                continue
            # Necessary feasibility constraint: an observed logical use of the
            # displaced expert inside the gap would need a second byte source.
            if end.previous_demand > start.seq:
                counts["displaced_expert_requested"] += 1
                continue
            edge = (start.seq, end.seq)
            generations[edge] = (layer, slot, gen)
            relaxed.append(edge)
            if end.ready_since is None or end.ready_since >= start.seq:
                counts["unproven_ready"] += 1
                continue
            if any(end.old in uses[t, layer] for t in range(start.tile, end.tile + 1)):
                counts["conservative_tile_pin"] += 1
                continue
            eligible.append(edge)
    schedule = simultaneous(eligible)
    if counts["candidates"] != 184:
        raise ValueError("trace disagrees with the #44 candidate inventory")
    return {
        "candidate_partition": dict(counts),
        "optimistic_matching_upper_for_fixed_destination": len(simultaneous(relaxed)),
        "individually_certifiable": len(eligible),
        "optimistic_load_union": [generations[edge] for edge in relaxed],
        "schedule": schedule,
        "load_generations": [generations[edge] for edge in schedule],
    }
