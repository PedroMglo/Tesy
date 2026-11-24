"""Verify an offline same-slot certificate against the ordered C135 journal.

Unobserved initial slots have the same symbolic payload in both executions.
READY establishes its immutable GGUF identity. Shadow policy operations remain
ordered exactly as recorded; the candidate differs only in the payload writes.
No timestamp is used to infer a pin, an initial expert or a saved duration.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass

N_SLOTS = 40
PART_BYTES = 4_406_400
EXPERT_BYTES = 3 * PART_BYTES
COMPONENT_OPS = ("READ_BEGIN", "READ_END", "TENSOR_SET_BEGIN", "TENSOR_SET_RETURN")
LOAD_OPS = ("DEQUEUE", "LOAD_BEGIN", *COMPONENT_OPS * 3, "LOAD_END")


def check(condition, message):
    if not condition:
        raise ValueError(message)


def identity(layer, expert):
    return tuple((layer, expert, component) for component in range(3))


@dataclass
class Reservation:
    expert: int
    call: int
    generation: int | None = None
    cursor: int = 0
    suppressed: bool = False


def tile_uses(events):
    tile, last_layer = -1, 36
    widths, positions, uses = [], {}, defaultdict(set)
    for event in events:
        if event["call_id"] != 2:
            continue
        layer = event["layer"]
        if event["kind"] == "DEMAND":
            if layer < last_layer:
                check(layer == 0 and event["wave"] in (-1, 0), "ambiguous tile start")
                tile += 1
                widths.append(event["n_tokens"])
            last_layer = layer
            uses[tile, layer].add(event["expert"])
        positions[event["seq"]] = tile
    check(widths == [32, 32, 32, 32, 20], "incomplete call-2 numerical tiles")
    return positions, uses


def verify(rows, schedule):
    """Return counts for a jointly valid witness, raise ValueError otherwise."""
    events = []
    for event in rows:
        events.append(event)
        if event["kind"] == "CALL_END" and event["call_id"] == 3:
            break
    by_seq = {event["seq"]: event for event in events}
    check(list(by_seq) == list(range(len(events))), "missing, duplicated or unordered events")
    check([e["n_tokens"] for e in events if e["kind"] == "CALL_BEGIN"] == [5, 148, 1]
          and [e["call_id"] for e in events if e["kind"] == "CALL_END"] == [1, 2, 3],
          "missing prefill/first decode boundary")
    positions, uses = tile_uses(events)
    starts, ends = {}, {}
    for source, target in schedule:
        check(source in by_seq and target in by_seq and source < target, "invalid endpoints")
        check(source not in starts and source not in ends and target not in starts
              and target not in ends, "reused endpoint")
        a, b = by_seq[source], by_seq[target]
        check(a["kind"] == b["kind"] == "EVICT" and a["call_id"] == b["call_id"] == 2,
              "endpoint outside a call-2 eviction")
        layer = a["layer"]
        check(a["expert"] == b["victim"] and a["expert"] != b["expert"]
              and layer == b["layer"] and a["slot"] != b["slot"], "incompatible substitution")
        first, last = positions[source], positions[target]
        check(0 <= first <= last, "unknown endpoint tile")
        check(all(b["expert"] not in uses[tile, layer] for tile in range(first, last + 1)),
              "displaced expert may be consumed or parked in a touched tile")
        starts[source] = b
        ends[target] = a

    baseline, candidate = {}, {}   # layer/slot -> component identities
    ready, pending, due = {}, {}, {}  # Shadow policy is shared by construction.
    loans, used_tiles = {}, defaultdict(set)
    last_gen, last_hit_or_load = {}, {}
    counts = Counter()
    avoided = Counter()
    generations = []
    checkpoints = []
    for e in events:
        kind, seq, call = e["kind"], e["seq"], e["call_id"]
        layer, slot, expert = e["layer"], e["slot"], e["expert"]
        place, logical = (layer, slot), (layer, expert)
        gen, wanted = e["generation"], identity(layer, expert)
        if kind == "CALL_END" and call in (2, 3):
            check(not loans and not due and not pending and baseline == candidate,
                  "payload divergence or outstanding generation at return")
            checkpoints.append(call)
            continue
        if kind in {"DEMAND", "PRELOAD", "EVICT", "RESERVE", "ENQUEUE", *LOAD_OPS}:
            check(0 <= layer < 36 and 0 <= expert < 128, "invalid logical identity")
            check(0 <= slot < N_SLOTS or (kind == "DEMAND" and slot == -1 and e["state"] == 0),
                  "invalid physical slot")
        if kind == "DEMAND":
            if call == 2:
                used_tiles[logical].add(positions[seq])
            if call == 3:
                counts["first_decode_demands"] += 1
            if place in loans and place not in pending:
                raise ValueError("demand while slot is privately borrowed")
            if e["state"] != 2:
                continue
            # An initial hit identifies otherwise unknown, equal initial bytes.
            check(place not in pending and place not in due, "READY during a replacement")
            check(baseline.setdefault(place, wanted) == wanted
                  and candidate.setdefault(place, wanted) == wanted, "demand payload mismatch")
            ready[place] = expert
            last_hit_or_load[logical] = (call, positions.get(seq, -1))
        elif kind == "PRELOAD":
            check(place not in loans or place in pending, "preload into privately borrowed slot")
        elif kind == "EVICT":
            check(e["state"] == 2 and place not in due and place not in pending,
                  "eviction not READY or generation still writing")
            check(baseline.setdefault(place, wanted) == wanted, "baseline victim mismatch")
            candidate.setdefault(place, wanted)
            if seq in ends:
                check(loans.get(place) == seq and candidate[place] == identity(layer, e["victim"]),
                      "borrowed payload missing at target")
            else:
                check(place not in loans and candidate[place] == wanted,
                      "intermediate eviction or source payload conflict")
            if seq in starts:
                b = starts[seq]
                dst = (layer, b["slot"])
                check(ready.get(dst) == b["expert"] and dst not in loans and dst not in pending
                      and dst not in due and baseline.get(dst) == candidate.get(dst)
                      == identity(layer, b["expert"]),
                      "destination lacks a proven idle READY owner")
                candidate[dst] = candidate[place]  # Three same-device components, before overwrite.
                loans[dst] = b["seq"]
            due[place] = (call, e["victim"], seq in ends)
            ready.pop(place, None)
        elif kind == "RESERVE":
            check(place in due and due[place][:2] == (call, expert), "reservation mismatch")
            _, _, suppress = due.pop(place)
            check(place not in loans or suppress, "write into live borrowed slot")
            pending[place] = Reservation(expert, call, suppressed=suppress)
            baseline[place] = (None,) * 3
            if not suppress:
                candidate[place] = baseline[place]
        elif kind == "ENQUEUE":
            r = pending.get(place)
            check(r is not None and (r.call, r.expert) == (call, expert),
                  "enqueue identity mismatch")
            if r.generation is None:
                check(gen > last_gen.get(place, 0), "non-advancing slot generation")
                last_gen[place] = gen
                r.generation = gen
            check(gen == r.generation, "generation changed during a reservation")
        elif kind in LOAD_OPS:
            r = pending.get(place)
            check(r is not None and (r.call, r.expert, r.generation) == (call, expert, gen),
                  "worker identity mismatch")
            check(kind == LOAD_OPS[r.cursor], "incomplete or reordered component transaction")
            if kind == "LOAD_BEGIN":
                check(e["logical_bytes"] == EXPERT_BYTES, "invalid load size")
                if r.suppressed:
                    previous_call, previous_tile = last_hit_or_load.get(logical, (-1, -1))
                    check(previous_call == 2 and previous_tile < positions[seq]
                          and any(tile < positions[seq] for tile in used_tiles[logical]),
                          "target had no earlier tile consumer in call 2")
                last_hit_or_load[logical] = (call, positions.get(seq, -1))
                if call == 3:
                    counts["first_decode_loads"] += 1
            elif kind in COMPONENT_OPS:
                part = (r.cursor - 2) // len(COMPONENT_OPS)
                check((e["component"], e["logical_bytes"]) == (part, PART_BYTES),
                      "component identity or length mismatch")
                if kind == "TENSOR_SET_RETURN":
                    updated = list(baseline[place])
                    updated[part] = wanted[part]
                    baseline[place] = tuple(updated)
                    if r.suppressed:
                        check(candidate[place][part] == wanted[part], "copied component mismatch")
                    else:
                        candidate[place] = baseline[place]
            elif kind == "LOAD_END":
                check(e["logical_bytes"] == EXPERT_BYTES and baseline[place] == candidate[place]
                      == wanted, "incomplete generation publication")
                if r.suppressed:
                    del loans[place]
                    tier = "CPU" if layer < 25 else "CUDA0"
                    avoided[tier] += 1
                    generations.append([layer, slot, gen])
                ready[place] = expert
                del pending[place]
            r.cursor += 1
    check(len(generations) == len(starts) and checkpoints == [2, 3], "unsettled certificate")
    return {"verified_pairs": len(starts), "loads_avoided": dict(avoided),
            "avoided_logical_read_bytes": len(starts) * EXPERT_BYTES,
            "same_tier_copy_payload_bytes": len(starts) * EXPERT_BYTES,
            "load_generations": generations, "equal_payload_at_call_ends": checkpoints,
            "first_decode_demands": counts["first_decode_demands"],
            "first_decode_loads": counts["first_decode_loads"]}
