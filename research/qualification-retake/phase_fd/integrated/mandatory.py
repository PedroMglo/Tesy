"""Conditional service floor for cold, same-wave, demand-only releases."""

from collections import Counter, defaultdict


def need(condition, error):
    if not condition:
        raise ValueError(error)


def lower_bound(services):
    if not services:
        return 0
    return max(max(services), sum(services) // 4)


def evaluate(rows, raw, public, clock):
    # Two passes distinguish an earlier preload from the first own-wave release.
    initial = {(r.layer, r.expert) for r in rows if r.kind == 5 and r.a}
    known = set(initial)
    reserve, demand, enqueue = {}, {}, {}
    spans = {}
    reads = defaultdict(list)
    saved = set()
    for r in rows:
        key = (r.layer, r.expert, r.slot, r.gen)
        site = (r.call, r.tile, r.layer, r.wave)
        if r.kind == 9:
            spans[site] = [r.ns]
        elif r.kind == 23:
            spans[site].append(r.ns)
        elif r.kind == 11:
            pair = (r.layer, r.expert)
            if pair not in known:
                saved.add(key)
                known.add(pair)
                reserve[key] = site
        elif r.kind == 10 and key in saved:
            demand.setdefault(key, site)
        elif r.kind == 12 and key in saved:
            enqueue.setdefault(key, (site, r.a))
        elif r.kind == 15 and key in saved:
            reads[key].append(r)
    group = defaultdict(list)
    exclusions = Counter()
    for k in saved:
        site = reserve[k]
        if k not in demand or enqueue.get(k) != (site, 0) or demand[k] != site:
            exclusions["free_preload_or_other_wave_or_unused"] += 1
            continue
        values = reads[k]
        begin, end = spans[site]
        need(
            len(values) == 3
            and len({r.worker for r in values}) == 1
            and {r.component for r in values} == {0, 1, 2}
            and all(begin <= r.begin <= r.ns <= end for r in values)
            and all(a.ns <= b.begin for a, b in zip(values, values[1:], strict=False)),
            "compulsory reads not serial inside own wave",
        )
        group[site].append(sum(r.ns - r.begin for r in values))
    start = int(raw["request_started_monotonic"] * 10**9)
    first = start + int(raw["stream_metrics"]["first_final_content_chunk_s"] * 10**9)
    buckets = Counter()
    jobs = Counter()
    for site, service in group.items():
        floor = lower_bound(service)
        if site[0] >= 3:
            buckets["decode"] += floor
            jobs["decode"] += len(service)
        else:
            buckets["prefill"] += floor
            jobs["prefill"] += len(service)
        # Leave the full crossing callback free in the lower bound.
        begin, end = spans[site]
        if begin >= start + 10**6 and end <= first - 10**6:
            buckets["first"] += floor
            jobs["first"] += len(service)
    unions = clock["unions"]["remap"]
    # Round outward in the candidate's favor.
    residual = {
        "first": first - start - 10**6 - unions["until_first_final_ns"],
        "decode": int(public["decode_s"] * 10**9) - unions["in_decode_ns"],
    }
    thresholds = {"first": 10**10, "decode": (47 * 10**9 + 5) // 6}
    result = {}
    for scale in (1.0, 0.8, 0.5):
        costs = {k: residual[k] + int(scale * buckets[k]) for k in residual}
        result[str(scale)] = {
            "first_final_floor_ns": costs["first"],
            "decode_floor_ns": costs["decode"],
            "decision": "NO_GO_FIXED_RELEASE_AND_REMAINDER"
            if any(v > thresholds[k] for k, v in costs.items())
            else "HEADROOM_ONLY",
        }
    return {
        "scenarios": result,
        "mandatory_floor_ns": dict(buckets),
        "required_jobs": dict(jobs),
        "free_first_reservations": dict(exclusions),
        "fixed_outside_callbacks_ns": residual,
        "max_service_scale": {
            k: (thresholds[k] - residual[k]) / buckets[k] if buckets[k] else None for k in residual
        },
    }
