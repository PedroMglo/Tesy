"""Read the C304 suffix only after all four pre-decode selections are sealed."""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(UNIT), str(UNIT.parent.parent / "tools")]

EXPERT_BYTES = 13_219_200
SCALES = (("1", 1, 1), ("0.8", 4, 5))


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def keyset(rows):
    keys = set()
    for row in rows:
        need(len(row) == 2 and all(type(x) is int for x in row), "invalid selection")
        layer, expert = row
        need(
            0 <= layer < 36 and 0 <= expert < 128 and (layer, expert) not in keys,
            "invalid or repeated key",
        )
        keys.add((layer, expert))
    return keys


def services(rows, data, residents):
    from primary_backing import screen as backing

    jobs, barriers, tail, native, initial, late, start = data
    need(not initial and not late, "undrained entry")
    markers, ranks, components = backing.markers(rows)
    seen = [set(v) for v in residents]
    prior = start
    work, order, used = [], [], set()
    tiers = {key: Counter() for key in ("CPU", "CUDA0")}
    for i, group in enumerate(barriers):
        key = call, layer = group["call"], group["layer"]
        need((call - 1, layer) == divmod(i, 36), "route order")
        z = markers.pop(key)
        ids_states = ranks.pop(key)
        ids = [e for e, _ in ids_states]
        order.append([call, layer, ids])
        need(
            set(z) in ({2, 14}, {2, 11, 12, 14})
            and prior <= z[2] <= z[14] == group["original_ready"],
            "invalid remap",
        )
        wait = (z[11], z[12]) if 11 in z else None
        need(wait is None or z[2] <= wait[0] <= wait[1] <= z[14], "wait outside remap")
        fixed = group["pre"] + group["attention"] + group["after"]
        stall = wait[1] - wait[0] if wait else 0
        need(stall == group["wait"] and fixed + stall == z[14] - prior, "C295 nonwait partition")
        reads = {}
        for w in group["need"]:
            expert = w[1]
            j = jobs[w]
            need(
                w not in used
                and w[0] == layer
                and expert not in reads
                and j["owner"] == call
                and z[2] <= j["begin"] <= j["end"] <= z[14],
                "foreign, overlapping or repeated job",
            )
            used.add(w)
            cc = components.pop(w)
            need(set(cc) == {(c, k) for c in range(3) for k in (6, 7)}, "three component READs")
            spans = [(cc[c, 6], cc[c, 7]) for c in range(3)]
            need(
                j["begin"] <= spans[0][0]
                and spans[-1][1] <= j["end"]
                and sum(b - a for a, b in spans) == j["read"],
                "worker envelope",
            )
            reads[expert] = spans
        first = set(ids) - seen[layer]
        need(
            all(s in (0, 2) for _, s in ids_states)
            and set(reads) == {e for e, s in ids_states if s == 0},
            "actual missing/running/claimed work",
        )
        value = backing.contribution(seen[layer], ids, reads, wait)
        need(value["union_outside_wait_us"] <= fixed, "overlapping READ exceeds group remainder")
        remaining = {e: sum(max(0, b - a - 1) for a, b in reads[e]) for e in first}
        need(
            max(remaining.values(), default=0) == value["required_read_floor_us"],
            "zero-choice control",
        )
        work.append((layer, remaining))
        tiers["CPU" if layer < 25 else "CUDA0"].update(value, nonwait_us=fixed, wait_us=stall)
        prior = z[14]
    need(
        len(work) == 1152
        and not ranks
        and not components
        and not markers
        and used == {w for w, j in jobs.items() if j["owner"] > 0},
        "decode coverage",
    )
    totals = sum(tiers.values(), Counter())
    fixed = totals["nonwait_us"] + tail
    need(totals["wait_us"] + fixed == native, "native partition")
    return work, dict(
        actual_decode_us=int(native),
        nonwait_including_tail_us=fixed,
        tail_us=tail,
        required_read_union_outside_wait_us=totals["union_outside_wait_us"],
        charged_fixed_us=fixed - totals["union_outside_wait_us"],
        tiers=tiers,
        groups=len(work),
        routes=4 * len(work),
        ordered_rank_sha256=backing.boundary.digest(order),
    )


def scales(read, fixed):
    from primary_backing.screen import score

    out = {}
    for label, n, d in SCALES:
        v = score(read, fixed, n, d)
        out[label] = {
            "reaches": not v["excludes"],
            "seconds": v["seconds"],
            "slack_seconds": -v["excess_seconds"],
        }
    return out


def evaluate_choices(groups, selected, fixed):
    from primary_entry_timing.solver import solve

    eligible = {(layer, e) for layer, row in groups for e in row}
    need(sum(len(row) for _, row in groups) == len(eligible), "first uses must be disjoint")
    counts = Counter(layer for layer, e in selected)
    caps = [counts[layer] for layer in range(36)]
    tiers = {}
    for which in ("CPU", "CUDA0"):
        rows = [(layer, row) for layer, row in groups if (layer < 25) == (which == "CPU")]
        seed = {k for k in selected if (k[0] < 25) == (which == "CPU")}
        base = sum(max(row.values(), default=0) for _, row in rows)
        rest = sum(
            max((us for e, us in row.items() if (layer, e) not in seed), default=0)
            for layer, row in rows
        )
        tiers[which] = dict(
            choices=len(seed),
            first_misses_removed=len(seed & eligible),
            unused_choices=len(seed - eligible),
            initial_payload_if_materialized=len(seed) * EXPERT_BYTES,
            base_required_read_floor_us=base,
            remaining_required_read_floor_us=rest,
            barrier_gain_us=base - rest,
        )
    base = sum(v["base_required_read_floor_us"] for v in tiers.values())
    rest = sum(v["remaining_required_read_floor_us"] for v in tiers.values())
    # solve returns the first threshold-crossing k; maximum_gain_us is the optimum over ALL budgets.
    oracle = solve(groups, caps, eligible, 0, 1, 1)
    oracle_rest = base - oracle["maximum_gain_us"]
    need(0 <= oracle_rest <= rest <= base, "equal per-layer-cap oracle or K=0")
    if not selected:
        need(rest == oracle_rest == base and oracle["k"] == 0, "zero choice must preserve baseline")
    return dict(
        tiers=tiers,
        count=len(selected),
        per_layer_caps=caps,
        read_floor_us=rest,
        barrier_gain_us=base - rest,
        capacity_bytes=len(selected) * EXPERT_BYTES,
        scopes_without_prepare_us=base,
        scales=scales(rest, fixed),
        oracle_same_layer_counts=dict(
            maximum_gain_us=base - oracle_rest,
            remaining_us=oracle_rest,
            scales=scales(oracle_rest, fixed),
        ),
    )


def evaluate_arm(raw_dir: Path, name: str, selected: dict, baseline: dict):
    from expert_prediction_holdout_gate import extract_prefix, prefix_events
    from primary_backing import screen as backing

    boundary = backing.boundary
    root = raw_dir / (name + ".native")
    need(
        set(selected["raw_sha256"]) == {"initial.json", "result.json", "events.tsv"},
        "sealed inputs",
    )
    for filename, h in selected["raw_sha256"].items():
        need(sha(root / filename) == h, "input changed after selection: " + filename)
    initial = json.loads((root / "initial.json").read_bytes())
    result = json.loads((root / "result.json").read_bytes())
    with (root / "events.tsv").open() as journal:
        residents, anchor = boundary.replay(initial, result, journal)
    need(
        anchor["boundary_slot_vector_sha256"] == selected["I_sha256"]
        and [sorted(v) for v in residents] == selected["initial_residents"],
        "independent I replay",
    )
    broad, narrow = (keyset(selected[k]) for k in ("reload_twice", "reload_last"))
    need(
        narrow <= broad and all(e not in residents[layer] for layer, e in broad),
        "selection overlaps I",
    )
    source = "control" if name.endswith("-1-greedy") else "estimator"
    need(
        name.endswith(("-1-greedy", "-2-estimate"))
        and baseline
        and baseline["investment_window_valid"],
        "official case",
    )
    official = baseline[source]
    need(
        official["measurement_valid"]
        and result["decode_calls"] == official["decode_calls"] == 32
        and result["case"] == official["case"]
        and result["teacher_forced_ids"] == result["native_argmax_ids"][:32]
        and all(result[k] == v for k, v in official["native_timings"].items()),
        "native window or trajectory",
    )
    rows = prefix_events(root / "events.tsv", True, 32)
    data = extract_prefix(rows, 32)
    groups, facts = services(rows, data, residents)
    controls = {}
    for v in baseline["sensitivity"]:
        s = v["service_scale"]
        replay = backing.c295.simulate(data, None, s, 128 << 20)
        if source == "control":
            need(replay == v["baseline"], "official greedy C304 baseline")
        controls[str(s)] = replay["decode_us"]
    need(set(controls) == {"0.8", "1.0", "1.2"}, "official scale coverage")
    fixed = facts["charged_fixed_us"]
    base = sum(max(j.values(), default=0) for _, j in groups)
    scopes = {
        k: evaluate_choices(groups, v, fixed)
        for k, v in (("reload_twice", broad), ("reload_last", narrow))
    }
    need(
        scopes["reload_twice"]["read_floor_us"] <= scopes["reload_last"]["read_floor_us"] <= base,
        "nested choices",
    )
    return dict(
        **facts,
        raw_sha256=selected["raw_sha256"],
        I_sha256=selected["I_sha256"],
        P_sha256=boundary.digest(boundary.slots(initial)),
        F_sha256=boundary.digest(boundary.slots(result["final"])),
        ordered_greedy_ids_sha256=boundary.digest(result["native_argmax_ids"]),
        native_decode_window_s=result["decode_window_s"],
        simulated_full_service_us=controls,
        official_greedy_baseline_verified=(source == "control"),
        r0_decode_loads=anchor["counts"]["decode_miss"],
        relaxed_without_selection=dict(read_floor_us=base, scales=scales(base, fixed)),
        scopes=scopes,
        real_victims_selected=0,
        induced_misses_timed=False,
        final_restoration_timed=False,
    )
