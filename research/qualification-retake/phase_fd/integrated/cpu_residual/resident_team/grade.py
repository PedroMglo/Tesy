"""Reconcile 24 MMID nodes and eight GGML lanes against a single graph clock."""

from statistics import median


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def union(intervals):
    stop = -1
    total = 0
    for a, b in sorted(intervals):
        need(0 < a < b, "reversed interval")
        total += max(0, b - max(stop, a))
        stop = max(stop, b)
    return total


def iteration(row, mode, expected_on, io_tids, inherited):
    start, end = row["start_ns"], row["end_ns"]
    need(
        row["on"] is expected_on and 0 < start < end and row["publish_ns"] > 0,
        "iteration endpoints",
    )
    need(row["fresh_hits"] == 5 and row["hot_reads"] == row["hot_sets"] == 0, "not a warm pass")
    marks = row["rows"]
    masks = {int(k): v for k, v in row["compute_masks"].items()}
    if not expected_on:
        need(not marks and not masks, "OFF events")
        return {"wall_ns": end - start}
    expected = {(w, r, i) for w in range(8) for r in range(3) for i in range(8)}
    need(
        len(marks) == 192 and {(w, r, i) for w, r, i, *_ in marks} == expected,
        "MMID/lane population",
    )
    lane_tids = {}
    intervals = {}
    migrations = 0
    for wave, role, lane, nth, tid, ca, cb, a, b in marks:
        need(nth == 8 and start <= a < b <= end and tid not in io_tids, "thread or clock")
        need(lane_tids.setdefault(lane, tid) == tid, "changed thread for GGML lane")
        expect = inherited if mode == "R" else [(4 if mode == "A" else 0) + lane]
        need(masks.get(tid) == expect and ca in expect and cb in expect, "effective CPU mask")
        migrations += int(ca != cb)
        intervals.setdefault((wave, role), []).append((a, b))
    need(
        len(set(lane_tids.values())) == 8 and set(lane_tids.values()) == set(masks),
        "eight unique TIDs",
    )
    node = [(min(a for a, b in group), max(b for a, b in group)) for group in intervals.values()]
    need(union(node) == sum(b - a for a, b in node), "neighboring MMID nodes overlap")
    wall = sum(union(group) for group in intervals.values())
    return dict(
        wall_ns=end - start,
        mmid_union_ns=wall,
        active_wave_union_ns=sum(union(g) for (w, _), g in intervals.items() if w == 0),
        parked_waves_union_ns=sum(union(g) for (w, _), g in intervals.items() if w > 0),
        summed_lane_wall_ns=sum(b - a for g in intervals.values() for a, b in g),
        other_graph_wall_ns=end - start - wall,
        different_cpu_endpoints=migrations,
        mask_by_tid=masks,
        compute_tids_by_lane=lane_tids,
    )


def verify(row, mode, stock, provider_paths):
    need(
        row["status"] == "PASS_C266_RESIDENT_TEAM_ARM"
        and row["team"] == mode
        and row["stock"] is stock,
        "native arm",
    )
    need(row["providers"] == provider_paths, "DL provider")
    need(
        row["router_positions"] == 153
        and row["finite_ffn_values_per_call"] == 92160
        and row["mmids"] == 24
        and row["active_waves"] == 1
        and row["manager_destructor_returned"]
        and row["workers_before_destructor"] == row["joined_workers"] == 4,
        "graph/worker contract",
    )
    empty = (-1, 0, 0, 0)
    s = row["slots"]
    slots = list(zip(s["owners"], s["generations"], s["states"], s["claims"], strict=True))
    vals = [e for e, g, state, c in slots if g == 1 and state == 2 and c == 0]
    need(
        len(slots) == 40 and slots.count(empty) == 35 and sorted(vals) == [45, 49, 57, 60, 98],
        "holders",
    )
    need(
        row["cold"] == {"reads": 5, "sets": 15, "returned_bytes": 66109440, "set_bytes": 66096000},
        "cold I/O",
    )
    inherited = row["inherited"]
    io = {tid for tid, _ in row["io_workers"]}
    need(
        len(io) == len(row["io_workers"]) == 4
        and all(m == inherited for _, m in row["io_workers"]),
        "wrong IO placement",
    )
    sequence = [False, False, False, False] if stock else [False, True, True, False]
    clocks = [
        iteration(r, mode, on, io, inherited) for r, on in zip(row["runs"], sequence, strict=True)
    ]
    off = median(r["wall_ns"] for r, on in zip(clocks, sequence, strict=True) if not on)
    on = (
        None
        if stock
        else median(r["wall_ns"] for r, on in zip(clocks, sequence, strict=True) if on)
    )
    return dict(
        team=mode,
        stock=stock,
        iterations=clocks,
        off_median_ns=off,
        on_median_ns=on,
        on_over_off=None if stock else on / off,
        slots=slots,
        io_workers=row["io_workers"],
        graph=[row["graph_fingerprint"], row["graph_nodes"], row["backend_splits"]],
        setup_ns=row["pool_setup_ns"],
        publish_ns=[r["publish_ns"] for r in row["runs"]],
    )


def decision(arms):
    need(
        [a["team"] for a in arms] == list("RRABBAR")
        and [a["stock"] for a in arms] == [True] + [False] * 6,
        "paired order",
    )
    need(
        all(a["slots"] == arms[0]["slots"] and a["graph"] == arms[0]["graph"] for a in arms),
        "state/graph differs",
    )
    stock = arms[0]["off_median_ns"]
    control = [arms[i]["off_median_ns"] / stock for i in (1, 6)]
    ratios = [a["on_over_off"] for a in arms[1:]]
    stable = all(0.85 <= v <= 1.15 for v in control + ratios)
    out = dict(
        status="INCONCLUSIVE_OBSERVER" if not stable else "MEASURED_RESIDENT_TEAM",
        observer_ratios=ratios,
        stock_control_ratios=control,
        contrasts={},
    )
    if stable:
        for label, pairs in (("R_minus_B", ((1, 3), (6, 4))), ("A_minus_B", ((2, 3), (5, 4)))):
            delta = [arms[i]["off_median_ns"] - arms[j]["off_median_ns"] for i, j in pairs]
            out["contrasts"][label] = dict(
                delta_ns=delta,
                direction=(
                    "B_SHORTER"
                    if min(delta) > 0
                    else "B_LONGER"
                    if max(delta) < 0
                    else "INCONCLUSIVE"
                ),
            )
    return out
