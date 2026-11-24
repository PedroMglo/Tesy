"""Offline whole-wave residency bounds for the frozen C135 call of 148 positions."""

from collections import Counter
from itertools import groupby

SLOTS = 40
HASH = "91610b12291d5a42a12bba09f5d4ff188d25ee0001ab89e894bdd508005e82fb"


def require(ok, why):
    if not ok:
        raise ValueError(why)


def snapshots(rows):
    """Infer only expert ID from witnesses in a slot-version interval; absent is unknown."""
    versions = Counter()
    ids = {}
    starts, ends = {}, {}
    evictions = {}

    def bind(version, expert):
        require(ids.get(version, expert) == expert, "inconsistent slot history")
        ids[version] = expert

    for r in rows:
        kind, call = r["kind"], r["call_id"]
        if kind == "CALL_BEGIN" and call == 2:
            starts = versions.copy()
        if kind == "CALL_END" and call == 2:
            ends = versions.copy()
        if kind not in ("RESERVE", "DEMAND", "EVICT"):
            continue
        layer, slot, expert = r["layer"], r["slot"], r["expert"]
        if slot < 0:
            continue
        k = layer, slot
        require(0 <= slot < SLOTS, "slot out of bounds")
        if kind == "RESERVE":
            replacing = evictions.pop(k, None)
            if replacing is None:
                bind((*k, versions[k]), -1)  # Empty old slot by the source EVICT guard.
            else:
                require(replacing == expert, "replacement disagrees with EVICT")
            versions[k] += 1
            bind((*k, versions[k]), expert)
        elif kind == "EVICT":
            require(r["state"] == 2, "evicted candidate not ready")
            bind((*k, versions[k]), expert)
            evictions[k] = r["victim"]
        elif r["state"] == 2:
            bind((*k, versions[k]), expert)
    require(not evictions, "unmatched EVICT")

    def decode(snapshot):
        return [
            [ids.get((layer, slot, snapshot.get((layer, slot), 0))) for slot in range(SLOTS)]
            for layer in range(36)
        ]

    return decode(starts), decode(ends)


def logical_waves(rows):
    layers = [[] for _ in range(36)]
    counts = Counter()
    previous = 36
    widths = []
    for r in rows:
        if r["call_id"] != 2:
            continue
        if r["kind"] == "LOAD_BEGIN":
            counts[r["layer"]] += 1
        if r["kind"] != "DEMAND":
            continue
        layer = r["layer"]
        if previous > layer:
            require(layer == 0 and r["wave"] in (-1, 0), "tile reset")
            widths.append(r["n_tokens"])
        previous = layer
        layers[layer].append(((len(widths) - 1, r["wave"]), r["expert"]))
    require(widths == [32, 32, 32, 32, 20], "unexpected tiles")
    grouped = []
    for layer in layers:
        waves = [
            (k, [item[1] for item in group]) for k, group in groupby(layer, key=lambda x: x[0])
        ]
        require(all(len(ids) == len(set(ids)) <= SLOTS for _, ids in waves), "invalid wave")
        grouped.append(waves)
    return grouped, counts


def wave_pins(waves, *, preload):
    requests = []
    for i, ((tile, wave), items) in enumerate(waves):
        required = set(items)
        if preload and wave >= 0:
            if len(items) < 4:
                require(
                    i and waves[i - 1][0] == (tile, wave - 1), "missing previous parking source"
                )
                required.update(waves[i - 1][1][: 4 - len(items)])
            if i + 1 < len(waves) and waves[i + 1][0][0] == tile:
                require(waves[i + 1][0][1] == wave + 1, "missing next nonempty wave")
                required.update(waves[i + 1][1])
        require(len(required) <= SLOTS, "overcommitted wave")
        requests.append(required)
    return requests


def farthest(initial, requests, capacity):
    """Belady for pin-all batched requests (evictions chosen outside the current set)."""
    cache = set(initial)
    require(len(cache) <= capacity, "initial set exceeds capacity")
    faults = []
    for t, needed in enumerate(requests):
        require(len(needed) <= capacity, "pinned set exceeds capacity")
        missing = needed - cache
        outside = cache - needed

        def next_use(x, t=t):
            return next(
                (i for i in range(t + 1, len(requests)) if x in requests[i]), len(requests)
            ), x

        victims = sorted(outside, key=next_use, reverse=True)[
            : max(0, len(cache) + len(missing) - capacity)
        ]
        cache.difference_update(victims)
        cache.update(needed)
        faults.append(sorted(missing))
    return faults


def place(initial, target, waves, policy="offline", *, oldest_highest=False):
    require(all(e != -1 for e in initial + target), "empty slot not covered")
    cache = initial[:]
    reqs = wave_pins(waves, preload=True)
    reqs.append(set(target) - {None})
    deadline = len(reqs)
    require(policy in ("offline", "lru"), "unknown replacement policy")
    order = list(range(len(cache)))
    if oldest_highest:
        order.reverse()
    last = {slot: age for age, slot in enumerate(order)}
    clock = len(order)
    loads = 0
    restore = 0
    for t, need in enumerate(reqs):
        missing = need - set(cache)

        def next_use(e, t=t):
            return next((i for i in range(t + 1, deadline) if e in reqs[i]), deadline)

        # Preserve physical home on a tie. The expert-order tiebreak may yield
        # different victim sets from farthest(), yet the offline optimum is equal.
        eligible = [s for s, e in enumerate(cache) if e is not None and e not in need]
        if policy == "offline":
            candidates = sorted(
                eligible, key=lambda s: (next_use(cache[s]), cache[s] != target[s], s), reverse=True
            )
        else:
            candidates = sorted(eligible, key=lambda s: (last[s], s))
        available = set(candidates[: len(missing)])
        require(len(available) == len(missing), "insufficient unpinned physical slots")
        allocated = {}
        at_end = t == deadline - 1
        if policy == "offline" or at_end:
            for s in sorted(available):
                if target[s] in missing:
                    allocated[s] = target[s]
        remaining = sorted(missing - set(allocated.values()))
        for s, e in zip(sorted(available - allocated.keys()), remaining, strict=True):
            allocated[s] = e
        for s, e in allocated.items():
            cache[s] = e
        require(need <= set(cache), "pin failure")
        if at_end:
            restore = len(missing)
        loads += len(missing)
        if policy == "lru":
            for expert in sorted(need):
                last[cache.index(expert)] = clock
                clock += 1
    wrong = {s for s, e in enumerate(cache) if e != target[s]}
    home = {e: s for s, e in enumerate(target) if e is not None}
    moves = len(wrong)
    cycles = 0
    while wrong:
        cycle = []
        s = min(wrong)
        while s in wrong:
            cycle.append(s)
            wrong.remove(s)
            s = home[cache[s]]
        require(s == cycle[0], "broken permutation")
        cycles += 1
        # Discard content of first; each remaining expert goes to its home
        # once by same-tier copy, and the discarded expert is reloaded once.
        hole = cycle[0]
        reload_expert = cache[hole]
        cache[hole] = None
        for source in reversed(cycle[1:]):
            require(home[cache[source]] == hole, "copy target mismatch")
            cache[hole], cache[source] = cache[source], None
            hole = source
        require(home[reload_expert] == hole, "reload target mismatch")
        cache[hole] = reload_expert
    require(cache == target, "physical mapping mismatch")
    return Counter(
        logical_loads=loads,
        endset_reads=restore,
        extra_restoration_reads=cycles,
        same_tier_slot_copies=moves - cycles,
        moved_slots=moves,
    )


def report(rows):
    incall = [r for r in rows if r["call_id"] == 2]
    local_i, local_f = snapshots(incall)
    initial, final = snapshots(rows)
    waves, load_counts = logical_waves(rows)
    out = []
    for n, wave in enumerate(waves):
        a, b = initial[n], final[n]
        known_i = {x for x in a if x is not None and x >= 0}
        known_f = {x for x in b if x is not None and x >= 0}
        require(
            sum(x is not None and x >= 0 for x in a) == len(known_i)
            and sum(x is not None and x >= 0 for x in b) == len(known_f),
            "duplicate expert in pool",
        )
        require(
            all((x is None) == (y is None) for x, y in zip(a, b, strict=True)),
            "unknown touched during call",
        )
        demand = set().union(*(set(order) for _, order in wave))
        # A resident that is accessed or overwritten during this call has a witness.
        # State-0 DEMAND cannot refer to an unobserved occupant. Unknown slots are
        # therefore irrelevant to the demanded working set, with their identity unchanged.
        owned_unknown = a.count(None)
        fields = {
            "layer": n,
            "historical_loads": load_counts[n],
            "initial_known_in_call": SLOTS - local_i[n].count(None),
            "final_known_in_call": SLOTS - local_f[n].count(None),
            "initial_known_full_trace": SLOTS - owned_unknown,
            "final_known_full_trace": SLOTS - b.count(None),
            "distinct_demands": len(demand),
            "demanded_absent_on_entry": len(demand - known_i),
        }
        for name, projected, endset, capacity in [
            ("demand_only", False, [], SLOTS),
            ("logical_endset", False, [known_f], SLOTS),
            ("preload_parking_endset_preserve_unknown", True, [known_f], SLOTS - owned_unknown),
        ]:
            req = wave_pins(wave, preload=projected) + endset
            faults = farthest(known_i, req, capacity)
            fields[name + "_loads"] = sum(map(len, faults))
            if endset:
                fields[name + "_restore_loads"] = len(faults[-1])
        for name, policy, high in (
            ("offline", "offline", False),
            ("lru_low_oldest", "lru", False),
            ("lru_high_oldest", "lru", True),
        ):
            realized = place(a, b, wave, policy, oldest_highest=high)
            if policy == "offline":
                require(
                    realized["logical_loads"]
                    == fields["preload_parking_endset_preserve_unknown_loads"],
                    "physical realization changed optimum",
                )
            fields.update({name + "_" + k: v for k, v in realized.items()})
        out.append(fields)
    return out


def evaluate(trace):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
    from c122_trace_validate import validate
    from c123_analyze_trace import sha, trace_rows

    require(sha(trace) == HASH, "trace digest")
    validate(trace)
    _, rows = trace_rows(trace)
    result = report(rows)
    totals = {}
    for tier, group in [("CPU", result[:25]), ("CUDA0", result[25:])]:
        totals[tier] = {k: sum(row[k] for row in group) for k in result[0] if k != "layer"}
    return {
        "schema": "c135-wave-residency-v1",
        "scope": "OFFLINE_TRACE_DERIVED",
        "trace_sha256": HASH,
        "expert_bytes": 13219200,
        "by_layer": result,
        "totals": totals,
    }


def main():
    import argparse
    from pathlib import Path

    from output import publish

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    publish(args.new_output_dir, lambda: evaluate(args.trace))


if __name__ == "__main__":
    main()
