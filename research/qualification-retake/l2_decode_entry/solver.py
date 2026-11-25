"""Exact relaxed seed selection at I plus finite encoded-cache interval witnesses."""

import sys
from collections import Counter, defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from l2_warm_critical.optimizer import resolve  # noqa: E402

BYTES = 13_219_200
TIERS = ("CPU", "CUDA0")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def valid_key(key):
    return (
        isinstance(key, tuple)
        and len(key) == 2
        and all(type(x) is int for x in key)
        and 0 <= key[0] < 36
        and 0 <= key[1] < 128
    )


def bind(jobs, groups, prefix_keys):
    """Bind group members to generations while allowing claim reordering within each group."""
    require(
        set(jobs) == {"increment", "decode"}
        and (prefix_keys is None or all(valid_key(k) for k in prefix_keys)),
        "phase or key",
    )
    increment, decode = list(jobs["increment"]), list(jobs["decode"])
    last_pub = {}
    used = set()
    last_claim = -1
    counts = {p: Counter() for p in ("increment", "decode")}
    for phase, items in (("increment", increment), ("decode", decode)):
        last_i = max(last_pub.values(), default=-1)
        for claim, pub, key in items:
            require(
                valid_key(key)
                and type(claim) is type(pub) is int
                and 0 <= claim < pub
                and last_claim < claim
                and used.isdisjoint((claim, pub)),
                "P5/P10 identity or order",
            )
            require(claim > last_pub.get(key, -1), "same-key concurrent service")
            require(phase != "decode" or claim > last_i, "I was not drained")
            counts[phase][TIERS[int(key[0] >= 25)]] += 1
            last_pub[key] = pub
            last_claim = claim
            used.update((claim, pub))
    inc = {key: pub for _, pub, key in increment}
    pending = defaultdict(deque)
    for entry in decode:
        pending[entry[2]].append(entry)
    grouped, marked = [], []
    seen = set()
    fence = -1
    for group in groups:
        services = []
        ends = []
        states = []
        for key, read, copy in group:
            require(valid_key(key) and pending[key], "C295 service absent, repeated or unknown")
            claim, pub, _ = pending[key].popleft()
            require(claim > fence, "C295 barriers overlap or are out of order")
            state = (
                "free"
                if key in seen
                else (
                    "eligible"
                    if key in inc or prefix_keys is None or key in prefix_keys
                    else "cold"
                )
            )
            states.append((key, read, copy, state))
            services.append((claim, read, copy))
            ends.append(pub)
            seen.add(key)
        if ends:
            fence = max(ends)
        grouped.append(services)
        marked.append(states)
    require(not any(pending.values()), "unmatched decode services")
    return inc, decode, counts, grouped, marked


def make_intervals(decode, inc, chosen):
    previous = {}
    intervals = []
    for begin, pub, key in decode:
        if key in previous:
            intervals.append((previous[key], begin, key, "decode"))
        elif key in chosen:
            origin = "increment" if key in inc else "P"
            intervals.append((inc.get(key, -1), begin, key, origin))
        previous[key] = pub
    return intervals


def witness(intervals, groups, baseline, capacity, limited, claims):
    events = []
    for start, stop, key, origin in intervals:
        events.extend(((start, 1, stop, key, origin), (stop, 0, stop, key, origin)))
    live = {}
    accepted = set()
    material = {phase: Counter({t: 0 for t in TIERS}) for phase in ("P", "increment", "decode")}
    hits = {phase: Counter({t: 0 for t in TIERS}) for phase in ("increment", "decode")}
    peak = dropped = 0
    for _, opening, claim, key, origin in sorted(events):
        tier = TIERS[int(key[0] >= 25)]
        if opening:
            require(key not in live, "overlapping retention of one expert")
            if limited and len(live) >= capacity:
                require(origin == "decode", "failed to preserve a chosen I resident")
                dropped += 1
            else:
                live[key] = claim
                material[origin][tier] += 1
                peak = max(peak, len(live))
        elif key in live:
            require(live.pop(key) == claim, "wrong retained generation")
            accepted.add(claim)
            hits["decode"][tier] += 1
    require(not live and len(accepted) + dropped == len(intervals), "service or final release")
    cost = sum(
        max((c if b in accepted else c + r for b, r, c in group), default=0) for group in groups
    )
    copies = sum(x for phase in material.values() for x in phase.values())
    require(copies == len(accepted), "admitted copy without matching consumption")
    return {
        "hit_claims": sorted(accepted),
        "group_max_sum_us": cost,
        "group_count": len(groups),
        "mean_group_max_us": cost / len(groups) if groups else 0,
        "occupied_at_I": sum(material[p][t] for p in ("P", "increment") for t in TIERS),
        "saved_vs_R0_us": baseline - cost,
        "fits": peak <= capacity,
        "peak_slots": peak,
        "peak_bytes": peak * BYTES,
        "final_slots": len(live),
        "hit_counts": hits,
        "materializations": material,
        "materialized_copies": copies,
        "materialized_bytes": copies * BYTES,
        "materialized_bytes_by_origin_tier": {
            p: {t: material[p][t] * BYTES for t in TIERS} for p in material
        },
        "RAM_to_staging_bytes": len(accepted) * BYTES,
        "primary_SET_bytes_by_phase_tier": {
            p: {t: claims[p][t] * BYTES for t in TIERS} for p in claims
        },
        "dropped_repeat_intervals": dropped,
    }


def solve(jobs, groups, prefix_keys, capacities):
    """Hold service durations fixed and charge the payload installed from P and later P10s."""
    prefix_keys = None if prefix_keys is None else set(prefix_keys)
    inc, decode, counts, bound, marked = bind(jobs, groups, prefix_keys)
    optimum = resolve(marked, capacities)
    r0 = sum(max((r + c for _, r, c in group), default=0) for group in bound)
    output = {}
    for k, solution in optimum.items():
        chosen = solution["chosen"]
        intervals = make_intervals(decode, inc, set(chosen))
        ideal = witness(intervals, bound, r0, k, False, counts)
        finite = witness(intervals, bound, r0, k, True, counts)
        require(
            ideal["group_max_sum_us"] == solution["group_max_sum_us"]
            and finite["fits"]
            and set(finite["hit_claims"]) <= set(ideal["hit_claims"]),
            "DP cost or finite witness inconsistent",
        )
        require(
            sum(finite["materializations"][p][t] for p in ("P", "increment") for t in TIERS)
            == len(chosen),
            "I membership was not materialized",
        )
        output[k] = {
            "chosen": chosen,
            "chosen_at_P": [key for key in chosen if key not in inc],
            "chosen_from_increment": [key for key in chosen if key in inc],
            "optimistic": ideal,
            "feasible": finite,
            "R0_group_max_sum_us": r0,
            "relaxed_gain_vs_empty_unlimited_repeat_us": solution["gain_us"],
        }
    return output
