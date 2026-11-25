"""Offline independent accounting of the C291 two-layer CPU offer/delivery experiment."""

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

ORDER = (
    ("EXACT", "OFF"),
    ("EXACT", "ON"),
    ("TIME", "OFF"),
    ("TIME", "ON"),
    ("TIME", "ON"),
    ("TIME", "OFF"),
)
OFFERS = [42, 19, 56, 113]
WINDOW = 13_221_888
SLAB = 4_406_400
FFN = (
    "b518f0dbd870d437f3e3b6275c89102daae3d65fe173bac58177f14677e88d52",
    "4d2dab8c357b4a27383736c122938fd6ea47a51aa3d30d08a18ecf68c14b5b8a",
)


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sealed(path, h):
    require(
        path.is_file() and not path.is_symlink() and path.stat().st_size <= 8 << 20,
        "regular bounded member " + path.name,
    )
    b = path.read_bytes()
    require(hashlib.sha256(b).hexdigest() == h, "digest " + path.name)
    return b


def merged(spans):
    """Disjoint half-open wall-time intervals. Touching endpoints add no overlap."""
    result = []
    for a, b in sorted(spans):
        require(type(a) is int and type(b) is int and 0 <= a <= b, "interval")
        if a == b:
            continue
        if result and a <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], b))
        else:
            result.append((a, b))
    return result


def intersect(left, right):
    a, b = merged(left), merged(right)
    i = j = 0
    out = []
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if lo < hi:
            out.append((lo, hi))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def length(xs):
    return sum(b - a for a, b in xs)


def peak(xs):
    changes = Counter()
    for a, b in xs:
        require(a <= b, "backwards worker interval")
        changes[a] += 1
        changes[b] -= 1
    n = height = 0
    for t in sorted(changes):
        n += changes[t]
        height = max(n, height)
    require(n == 0, "unbalanced worker intervals")
    return height


def overlap(spec, source, remaps, primary_read, primary_set):
    in_graph = intersect(spec, [source])
    in_remap = intersect(in_graph, remaps)
    on_read = intersect(in_graph, primary_read)
    on_set = intersect(in_graph, primary_set)
    return {
        "spec_read_summed_worker_ns": length(spec),
        "spec_read_wall_union_ns": length(merged(spec)),
        "spec_read_in_graph0_wall_ns": length(in_graph),
        "spec_read_in_graph0_summed_worker_ns": sum(length(intersect([p], [source])) for p in spec),
        "spec_read_in_graph0_remap_wall_ns": length(in_remap),
        "spec_read_in_graph0_outside_remaps_wall_ns": length(in_graph) - length(in_remap),
        "spec_read_in_graph0_with_L0_primary_read_wall_ns": length(on_read),
        "spec_read_in_graph0_with_L0_primary_set_wall_ns": length(on_set),
        "spec_read_in_graph0_with_either_primary_service_wall_ns": length(merged(on_read + on_set)),
    }


def stage_residency(events, graph0):
    """Bound occupancy of the speculative read stage; its steady clock truncates to µs."""
    times = defaultdict(dict)
    for kind, _, ticket, _, _, tick in events:
        if kind in (2, 3):
            require(kind not in times[ticket], "duplicate staged service endpoint")
            times[ticket][kind] = tick * 1000
    inner, outer = [], []
    for ends in times.values():
        require(set(ends) == {2, 3} and ends[2] <= ends[3], "incomplete stage")
        # Each recorded tick represents [tick, tick + 999] ns in steady_clock.
        outer.append((ends[2], ends[3] + 999))
        if ends[2] + 999 <= ends[3]:
            inner.append((ends[2] + 999, ends[3]))
    return {
        "dispatched": len(outer),
        "stage_in_graph0_wall_lower_ns": length(intersect(inner, [graph0])),
        "stage_in_graph0_wall_upper_ns": length(intersect(outer, [graph0])),
        "completed_by_graph0_end_certain": sum(v[3] + 999 <= graph0[1] for v in times.values()),
        "completed_by_graph0_end_possible": sum(v[3] <= graph0[1] for v in times.values()),
    }


def outcome(ns):
    require(len(ns) == 4 and all(type(n) is int and n > 0 for n in ns), "four times")
    deltas = [ns[0] - ns[1], ns[3] - ns[2]]
    if min(deltas) > 0:
        return deltas, "GO_NEXT_PAIR_FIXTURE"
    if max(deltas) < 0:
        return deltas, "NO_GO_TRAVERSAL_TIMING"
    return deltas, "INCONCLUSIVE_TRAVERSAL_TIMING"


def tickets(row, actual_spec, bindings):
    events = defaultdict(list)
    for kind, e, k, slot, gen, us in row["stage_events"]:
        require(e in OFFERS and k > 0 and us > 0 and kind != 9, "stage event")
        if kind in (7, 11):
            require((1, e, slot, gen) in bindings, "staged delivery binding")
        events[k].append((kind, e, us))
    ids, started, consumed, attached = set(), set(), set(), 0
    for values in events.values():
        kinds, experts, stamps = zip(*values, strict=True)
        e = experts[0]
        require(
            kinds[0] == 1
            and kinds.count(1) == 1
            and len(set(experts)) == 1
            and e not in ids
            and list(stamps) == sorted(stamps),
            "ticket epochs",
        )
        ids.add(e)
        if 2 in kinds:
            require(
                kinds.count(2) == kinds.count(3) == 1 and kinds.index(2) < kinds.index(3),
                "staged read",
            )
            started.add(e)
        if 8 in kinds:
            require(
                e in started
                and all(kinds.count(x) == 1 for x in (6, 7, 8))
                and kinds.index(6) < kinds.index(7) < kinds.index(8),
                "staged consumption",
            )
            consumed.add(e)
            attached += int(kinds.index(6) < kinds.index(3))
    stats = row["stage"]
    require(
        len(actual_spec) == len(set(actual_spec))
        and set(actual_spec) == started
        and len(ids) == stats["issued"]
        and len(started) == stats["reads"]
        and len(consumed) == stats["consumed"]
        and attached == stats["waits"],
        "stage vs syscall",
    )
    require((not ids if row["mode"] == "OFF" else ids == set(OFFERS)), "issued four or none")
    return consumed


def arm(row, grade, mode):
    e = row["epochs_ns"]
    require(
        row["status"] == "PASS_REAL_TILE"
        and (row["grade"], row["mode"]) == (grade, mode)
        and row["drained"] is True
        and row["workers"] == 4
        and row["offers"] == OFFERS,
        "native gate",
    )
    require(
        len(e) == 8
        and all(type(t) is int for t in e)
        and e == sorted(e)
        and row["elapsed_ns"] == e[-1] - e[0]
        and row["drain_ns"] == e[-1] - e[5],
        "endpoints",
    )

    def span(a, b):
        require(e[0] <= a <= b <= e[-1], "outside primary window")
        return (a, b)

    binds = {tuple(b) for b in row["slot_bindings"]}
    require(
        len(binds) == len(row["slot_bindings"]) == 125 and len({b[:2] for b in binds}) == 125,
        "125 distinct official assignments",
    )
    read = defaultdict(list)
    reads_by_key = Counter()
    actual_spec = []
    for layer, k, spec, a, b in row["reads"]:
        require(layer in (0, 1) and 0 <= k < 128 and spec in (0, 1) and a < b, "pread")
        read[layer, spec].append(span(a, b))
        reads_by_key[layer, k, spec] += 1
        if spec:
            require(layer == 1 and mode == "ON", "speculative source")
            actual_spec.append(k)
    consumed = tickets(row, actual_spec, binds)
    sets = defaultdict(list)
    by_binding = defaultdict(dict)
    for layer, k, s, g, component, a, b in row["service"]:
        key = (layer, k, s, g)
        require(
            key in binds and component in (0, 1, 2) and component not in by_binding[key],
            "SET binding/component",
        )
        by_binding[key][component] = span(a, b)
        sets[layer].append((a, b))
    require(len(by_binding) == 125 and row["sets"] == len(row["service"]) == 375, "SET population")
    for layer, k, s, g in binds:
        components = by_binding[layer, k, s, g]
        require(
            set(components) == {0, 1, 2}
            and components[0][1] <= components[1][0]
            and components[1][1] <= components[2][0],
            "ordered three SETs",
        )
        require(
            reads_by_key[layer, k, 0] == (0 if layer == 1 and k in consumed else 1),
            "disk vs staged supply",
        )
    require(
        set((layer, k) for layer, k, s in reads_by_key if not s) <= {b[:2] for b in binds},
        "extra primary read",
    )
    require(
        125 <= len(row["reads"]) == row["read_jobs"] <= 130
        and row["pread_bytes"] == len(row["reads"]) * WINDOW
        and row["slab_hashes"] == (3 * len(row["reads"]) if grade == "EXACT" else 0),
        "bytes and integrity",
    )
    waits = defaultdict(list)
    for layer, a, b in row["wait_intervals_us"]:
        require(layer in (0, 1) and a <= b, "C294 wait")
        waits[layer].append((a, b))
    require(sum(length(v) * 1000 for v in waits.values()) == row["wait_ns"], "wait sum")
    remaps = {}
    layers = {}
    sources = [(e[1], e[2]), (e[3], e[4])]
    for layer in (0, 1):
        key = f"L{layer}"
        numer = row["numeric"][key]
        require(
            numer["ffn_sha256"] == FFN[layer]
            and numer["ffn_words"] == 92160
            and numer["mmid_nodes"] == numer["bias_nodes"] == 24
            and numer["active_waves"] == 4
            and [w["wave"] for w in numer["waves"]] == list(range(8))
            and sum(w["active"] for w in numer["waves"]) == 128
            and all(w["parking_differences"] == 0 for w in numer["waves"]),
            "wave and numerical closure",
        )
        rs = [span(*s) for s in row["remap_ns"][key]]
        require(
            len(rs) == 8
            and rs == sorted(rs)
            and all(rs[i][1] <= rs[i + 1][0] for i in range(7))
            and sources[layer][0] <= rs[0][0] <= rs[-1][1] <= sources[layer][1],
            "host remap windows",
        )
        remaps[layer] = rs
        p, sp, st = read[layer, 0], read[layer, 1], sets[layer]
        require(len(st) == 3 * (66 if layer == 0 else 59), "SET count by layer")
        layers[key] = dict(
            primary_reads=len(p),
            spec_reads=len(sp),
            sets=len(st),
            read_bytes=(len(p) + len(sp)) * WINDOW,
            set_bytes=len(st) * SLAB,
            wait_calls=len(waits[layer]),
            wait_ns=length(waits[layer]) * 1000,
            remap_wall_ns=length(rs),
            read_summed_worker_ns=length(p + sp),
            read_wall_union_ns=length(merged(p + sp)),
            set_summed_worker_ns=length(st),
            set_wall_union_ns=length(merged(st)),
        )
    active = peak([z for vals in [*sets.values(), *read.values()] for z in vals])
    require(0 < active <= 4, "four-worker bound")
    intervals = [
        "project_and_submit",
        "graph0",
        "verify0",
        "graph1",
        "verify1",
        "finish_stage",
        "join_tail",
    ]
    epochs = {name: e[i + 1] - e[i] for i, name in enumerate(intervals)}
    return dict(
        mode=mode,
        grade=grade,
        elapsed_ns=row["elapsed_ns"],
        phase_ns=epochs,
        raw_projector_duration_ns=row["producer_ns"],
        layers=layers,
        staged_worker_lifetime=stage_residency(row["stage_events"], sources[0]),
        graph0_overlap=overlap(read[1, 1], sources[0], remaps[0], read[0, 0], sets[0]),
        stage=dict(row["stage"], wasted_reads=len(actual_spec) - len(consumed)),
        worker_peak_reads_or_sets=active,
        preloads=row["preloads"],
    )


def review(raw, expected):
    r = json.loads(sealed(raw / "receipt.json", expected))
    arms = []
    for i, record in enumerate(r["arms"]):
        require(i < len(ORDER) and (record["grade"], record["mode"]) == ORDER[i], "order")
        directory = raw / f"{i:02d}-{record['grade']}-{record['mode']}"
        copy = json.loads((directory / "receipt.json").read_bytes())
        require(copy == record, "arm receipt")
        for name in ("stdout", "stderr"):
            if name + "_sha256" in record:
                sealed(directory / name, record[name + "_sha256"])
        if record["status"] == "PASS_ARM":
            require(record["returncode"] == 0, "native exit")
            row = json.loads((directory / "stdout").read_bytes())
            analyzed = arm(row, *ORDER[i])
            require(
                row["elapsed_ns"] == record["elapsed_ns"]
                and row["stage"] == record["stage"]
                and row["pread_bytes"] == record["pread_bytes"]
                and row["sets"] == record["sets"],
                "summary",
            )
            signature = (row["numeric"], sorted(row["slot_bindings"]))
            if i == 0:
                previous = signature
            else:
                require(signature == previous, "changed bindings or numerical witness")
            arms.append(analyzed)
    if r["status"] == "FAIL_PRESERVED":
        return dict(
            status="REPRODUCED_PRESERVED_FAILURE",
            source_sha256=expected,
            reason=r.get("reason"),
            passed_arms=arms,
            decision="INCONCLUSIVE",
        )
    require(
        r["status"] == "PASS_REAL_TILE_FAMILY"
        and len(arms) == 6
        and r["swap_peak_bytes"] == 0
        and len(r["remaining_pids"]) == 1,
        "complete closed family",
    )
    deltas, decision = outcome([x["elapsed_ns"] for x in arms[2:]])
    require(deltas == r["paired_saved_ns"] and decision == r["decision"], "paired outcome")
    return dict(
        status="REPRODUCED_REAL_TILE_FAMILY",
        source_sha256=expected,
        decision=decision,
        commit=r["commit"],
        input_sha256=r["input_sha256"],
        build_sha256=r["build_sha256"],
        paired_off_minus_on_ns=deltas,
        arms=arms,
        clocks={
            "epochs_remaps_reads_sets": "one native steady_clock, ns",
            "waits": "C294 ggml_time_us durations only",
            "projector": "CLOCK_MONOTONIC_RAW duration only",
            "stage_events": "same staging journal, microseconds and ticket order",
        },
        excluded=[
            "attention/residual/router-1 execution",
            "GGML/worker CPU-time",
            "model chronology or natural client speed",
        ],
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", required=True, type=Path)
    ap.add_argument("--sha256", required=True)
    ap.add_argument("--new-output-dir", type=Path, required=True)
    a = ap.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        result = review(a.raw, a.sha256)
    except Exception as exc:
        result = {"status": "FAIL_REVIEW_PRESERVED", "reason": repr(exc)}
    (a.new_output_dir / "receipt.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
    print(result["status"], result.get("reason", result.get("decision", "")))
    raise SystemExit(int(result["status"] == "FAIL_REVIEW_PRESERVED"))
