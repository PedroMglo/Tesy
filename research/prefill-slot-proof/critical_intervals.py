"""Optimistic time bound from causal releases and deadlines within each tile/layer.

All demands, waves and order of controller work are frozen. Service can start
later and finish earlier relative to other jobs, with ideal worker assignment
and zero coordination. Original non-WAIT controller intervals supply only
lower bounds, so extra wait anywhere is allowed. Timestamps are in microseconds.
"""

from collections import Counter, defaultdict

from critical import generation, require, selection_keys, wave_inputs


def earliest_end(markers, wait_pairs, jobs):
    """Longest-path lower bound on the endpoint in a four-worker relaxation.

    For each job impose its service duration between release and consumer.
    For every [release, deadline] interval impose the summed durations of
    all retained jobs contained in it, divided by four. The controller still
    pays its non-WAIT work. Bounds accumulate on disjoint consecutive spans.
    """
    seqs = sorted(markers)
    index = {seq: i for i, seq in enumerate(seqs)}
    require(all(index[a] + 1 == index[b] for a, b in wait_pairs),
            "controller marker inside WAIT")
    at_deadline = defaultdict(list)
    for release, deadline, duration in jobs:
        require(release < deadline and duration >= 0, "invalid consumer deadline")
        at_deadline[index[deadline]].append((index[release], max(0, duration - 1)))
    ready = [0] * len(seqs)
    expired_volume = Counter()
    for end in range(1, len(seqs)):
        prev, cur = seqs[end - 1], seqs[end]
        gap = markers[cur] - markers[prev]
        require(gap >= 0, "controller clock reversed")
        delay = 0 if (prev, cur) in wait_pairs else max(0, gap - 1)
        ready[end] = ready[end - 1] + delay
        for start, duration in at_deadline[end]:
            ready[end] = max(ready[end], ready[start] + duration)
            expired_volume[start] += duration
        if at_deadline[end]:
            volume = 0
            for start in sorted(expired_volume, reverse=True):
                volume += expired_volume[start]
                ready[end] = max(ready[end], ready[start] + volume // 4)
    return ready[-1]


def interval_report(full_rows, selected=None, *, eligibility=None):
    rows = [row for row in full_rows if row["call_id"] == 2]
    candidates, demands, waits, service, first_enqueue, first_demand, load_scope = wave_inputs(rows)
    # The default universe is the frozen cross-tile gate. Another study may
    # supply its independently reconstructed identities from the same journal.
    if eligibility is not None:
        candidates = selection_keys(rows, eligibility)
    removed = candidates if selected is None else selection_keys(rows, selected)
    require(removed <= candidates, "credit outside selected admissible universe")
    changed = {load_scope[key] for key in removed}
    # The retained generation stays necessary only until its *first* use.
    # The original call can have demand-ready preloads with no WAIT at that
    # consumer wave. Grant them even the time until the next wave or layer's
    # first demand. The observed-state-independent upper endpoint is then
    # known by the graph edge consuming the previous wave before reservation.
    ready_at = {}
    resident = {}
    first_by_wave = {}
    last_callback = {}
    tile, prev = -1, 36
    for e in rows:
        kind, layer = e["kind"], e["layer"]
        where = layer, e["slot"]
        if kind == "DEMAND":
            if layer < prev:
                tile += 1
            prev = layer
            wave = tile, layer, e["wave"]
            first_by_wave.setdefault(wave, e["seq"])
            if e["state"] == 2 and where in resident:
                key = resident[where]
                require(key[1] == e["expert"], "ready expert differs from generation")
                ready_at.setdefault(key, wave)
        elif kind in ("EVICT", "RESERVE"):
            resident.pop(where, None)
        elif kind == "LOAD_END":
            resident[where] = generation(e)
        if kind in ("DEMAND", "PRELOAD", "RESERVE", "EVICT", "ENQUEUE", "WAIT_BEGIN", "WAIT_END"):
            last_callback[wave] = e["seq"]
    call_end = rows[-1]["seq"]
    seq_time = {e["seq"]: e["mono_us"] for e in rows}
    waves = list(first_by_wave)
    starts = list(first_by_wave.values())
    next_start = dict(zip(waves, starts[1:] + [call_end], strict=True))
    deadline = {}
    for wave, work in demands.items():
        for _, key in work:
            require(key not in deadline, "duplicate accepted-generation deadline")
            deadline[key] = waits[wave][-1]["seq"]
    for key, wave in ready_at.items():
        if load_scope[key] == wave[:2]:
            stop = waits[wave][-1]["seq"] if wave in waits else next_start[wave]
            deadline[key] = min(stop, deadline.get(key, stop))
    require(set(service) <= deadline.keys(), "generation has no same-scope consumer")
    jobs = defaultdict(list)
    points = defaultdict(dict)
    for key, duration in service.items():
        if key in removed:
            continue
        scope = load_scope[key]
        r = first_enqueue[key][0]
        d = deadline[key]
        jobs[scope].append((r, d, duration))
        points[scope].update({r: seq_time[r], d: seq_time[d]})
    pairs = defaultdict(set)
    wait_us = Counter()
    for wave, (a, b) in waits.items():
        scope = wave[:2]
        points[scope].update({a["seq"]: a["mono_us"], b["seq"]: b["mono_us"]})
        pairs[scope].add((a["seq"], b["seq"]))
        wait_us[scope] += b["mono_us"] - a["mono_us"] + 1
    layers = list(first_demand)
    layer_starts = [next(seq for wave, seq in first_by_wave.items() if wave[:2] == scope)
                    for scope in layers]
    bound = 0
    free_callback_bound = 0
    timed_scopes = 0
    for scope, first, last in zip(layers, layer_starts, layer_starts[1:] + [call_end], strict=True):
        if scope not in changed:
            continue
        points[scope].update({first: seq_time[first], last: seq_time[last]})
        require(min(points[scope]) == first and max(points[scope]) == last,
                "retained work escaped tile/layer")
        minimum_us = earliest_end(points[scope], pairs[scope], jobs[scope])
        elapsed = seq_time[last] - seq_time[first]
        require(minimum_us <= elapsed + 1, "relaxation cannot reproduce historical clock")
        bound += min(elapsed + 1 - minimum_us, wait_us[scope])
        # Additionally drop ALL controller cost between first demand and last
        # observed in-callback event at every wave of each affected scope.
        # These include the identifiable enqueue/reserve bookkeeping. Work
        # outside the observed wave intervals stays frozen in this sensitivity.
        boundaries = dict(points[scope])
        spans = [(first_by_wave[w], last_callback[w]) for w in waves if w[:2] == scope]
        for a, b in spans:
            boundaries.update({a: seq_time[a], b: seq_time[b]})
        sorted_seq = sorted(boundaries)
        free = {(x, y) for x, y in zip(sorted_seq, sorted_seq[1:], strict=False)
                if any(a <= x < y <= b for a, b in spans)}
        free_min = earliest_end(boundaries, free, jobs[scope])
        require(free_min <= elapsed + 1, "free-callback relaxation is inconsistent")
        total_window = sum(seq_time[b] - seq_time[a] + 1 for a, b in spans)
        free_callback_bound += min(elapsed + 1 - free_min, total_window)
        timed_scopes += 1
    return {"changed_tile_layers": timed_scopes,
            "retained_service_generations": len(service) - len(removed),
            "interval_capacity_saving_upper_us": bound,
            "free_observed_callback_saving_upper_us": free_callback_bound}
