"""Attribute warm-tile reads and SETs to the sealed restore, primary bindings and tickets."""

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
C = run_path(str(HERE.parent / "review.py"))
need, sealed, merged, length = (C[k] for k in ("require", "sealed", "merged", "length"))
WINDOW, SLAB, ORDER = C["WINDOW"], C["SLAB"], C["ORDER"]
OFFERS = (6, 13, 20, 21)
PREP = "64c6b08357cc2c03bd0959f417a6e3f905977b5a13be99b70b4b488354b3aa03"
PHASES = (
    "project_and_submit",
    "graph0",
    "verify0",
    "graph1",
    "verify1",
    "finish_stage",
    "join_tail",
)


def binding(r):
    return (r["layer"], r["expert"], r["slot"], r["gen"])


def intervals(rows):
    return [(r[-2], r[-1]) for r in rows]


def restore(raw, prep, t0):
    reads, sets = raw["records"], raw["set_intervals"]
    expected = [binding(r) for r in prep["warm_records"]]
    need(
        len(expected) == 80 and [tuple(r[:4]) for r in reads] == expected,
        "order/bindings of warm reads",
    )
    need(
        len(sets) == 240
        and [tuple(r[:5]) for r in sets] == [(*b, c) for b in expected for c in range(3)],
        "order/bindings of warm SETs",
    )
    end = 0
    for i in range(len(expected)):
        spans = intervals([reads[i], *sets[3 * i : 3 * i + 3]])
        for a, z in spans:
            need(0 < a <= z <= t0 and end <= a, "restore chronology")
            end = z
    need(
        raw["worker_acks"] == 4
        and raw["postset_checks"] == raw["slab_hashes"] == 240
        and all(
            raw[k] is True
            for k in ("initial_policy_verified", "terminal_policy_verified", "stale_tile_rejected")
        ),
        "warm physical state controls",
    )
    need(
        raw["preads"] == 80
        and raw["sets"] == 240
        and raw["pread_bytes"] == 80 * WINDOW
        and raw["set_bytes"] == 240 * SLAB
        and raw["elapsed_ns"] >= end - reads[0][-2] > 0,
        "warm paid bytes/time",
    )
    rd, st = length(intervals(reads)), length(intervals(sets))
    return dict(
        records=80,
        sets=240,
        pack_bytes=80 * WINDOW,
        primary_bytes=240 * SLAB,
        wall_ns=raw["elapsed_ns"],
        pread_ns=rd,
        set_ns=st,
        remaining_wall_ns=raw["elapsed_ns"] - rd - st,
        worker_acks=4,
        verified_sha_and_primary_slabs=240,
    )


def ticket_report(events, spec, binds, mode):
    grouped = defaultdict(list)
    last = -1
    for kind, expert, ticket, slot, gen, us in events:
        need(
            type(us) is int and us >= last and expert in OFFERS and ticket > 0,
            "stage identity/clock",
        )
        last = us
        if kind in (7, 11):
            need((1, expert, slot, gen) in binds, "stage binding of authoritative generation")
        else:
            need((slot, gen) == (-1, 0), "unexpected binding outside stage commit")
        grouped[ticket].append((kind, expert, us))
    need(
        [x[1] for x in events if x[0] == 1] == (list(OFFERS) if mode == "ON" else []),
        "submitted offers/order",
    )
    tickets, consumed, starts, counts = {}, set(), set(), Counter()
    patterns = {
        (1, 4): "queued_discard",
        (1, 2, 3, 4): "expired_ready",
        (1, 2, 5, 3, 4): "expired_running",
        (1, 2, 3, 6, 7, 11, 8): "consumed_ready",
        (1, 2, 6, 3, 7, 11, 8): "consumed_after_reading_wait",
    }
    for tid, log in grouped.items():
        seq = tuple(x[0] for x in log)
        expert = log[0][1]
        need(
            len({x[1] for x in log}) == 1 and expert not in tickets and seq in patterns,
            "ticket lifecycle",
        )
        reason = patterns[seq]
        ts = {k: t for k, _, t in log}
        counts["issued"] += 1
        pread_ns = 0
        if 2 in seq:
            starts.add(expert)
            need(expert in spec, "stage without matching pack pread")
            a, b = spec[expert]
            need(ts[2] * 1000 <= a <= b <= ts[3] * 1000 + 999, "pread outside claimed ticket")
            pread_ns = b - a
            counts["reads"] += 1
        if 8 in seq:
            need(expert == 20, "false ticket consumed")
            consumed.add(expert)
            counts["consumed"] += 1
        if reason == "queued_discard":
            if expert != 20:
                counts["expired_queued"] += 1
            else:
                reason = "queued_demand_fell_back_to_primary"
        elif reason.startswith("expired_"):
            counts[reason] += 1
        wait = None
        if reason == "consumed_after_reading_wait":
            counts["waits"] += 1
            # Event 6 attach and 3 producer completion are independently quantized to us.
            # Event 7 follows wake and recheck on the official worker.
            wait = dict(
                attach_to_read_done_ns=bound_us(ts[6], ts[3]),
                attach_to_claim_ns=bound_us(ts[6], ts[7]),
            )
        tickets[expert] = dict(
            ticket=tid,
            truth=expert == 20,
            result=reason,
            pack_bytes=WINDOW if 2 in seq else 0,
            pread_ns=pread_ns,
            wait=wait,
            stage_kinds=list(seq),
        )
    need(set(spec) == starts, "pack reads without stage ticket")
    return (
        tickets,
        consumed,
        {
            k: counts[k]
            for k in (
                "issued",
                "reads",
                "consumed",
                "waits",
                "expired_queued",
                "expired_ready",
                "expired_running",
            )
        },
    )


def bound_us(a, b):
    need(a <= b, "backward ticket stamps")
    return [max(0, (b - a) * 1000 - 999), (b - a) * 1000 + 999]


def numerical(row, prep):
    need(set(row["numeric"]) == {"L0", "L1"}, "two FFNs")
    for lnum in (0, 1):
        label = f"L{lnum}"
        m = row["numeric"][label]
        need(
            m["layer"] == lnum
            and m["ffn_words"] == 92160
            and m["mmid_nodes"] == m["bias_nodes"] == 24
            and len(m["waves"]) == 8
            and sum(w["active"] for w in m["waves"]) == 128
            and sum(w["active"] > 0 for w in m["waves"]) == m["active_waves"] == 3,
            "graph counts",
        )
        tests = {
            "x_sha256": "x.f32",
            "logical_sha256": "ids.i32",
            "mix_sha256": "mix.f32",
            "ffn_sha256": "ffn.f32",
        }
        for k, v in tests.items():
            need(m[k] == prep["file_sha256"][label + "." + v], "independent " + k)
        for i, w in enumerate(m["waves"]):
            need(i == w["wave"] and w["parking_differences"] == 0, "wrong parking/ordering")
            for k, v in (("physical", "ids.i32"), ("generation", "gen.u64"), ("mask", "mask.f32")):
                need(w[k + "_sha256"] == prep["file_sha256"][f"{label}.w{i}.{v}"], "wave " + k)


def analyze(row, grade, mode, prep):
    need(
        (row["status"], row["grade"], row["mode"], row["offers"], row["workers"], row["drained"])
        == ("PASS_WARM_TILE", grade, mode, list(OFFERS), 4, True),
        "arm provenance",
    )
    e = row["epochs_ns"]
    need(
        len(e) == 8
        and all(type(t) is int and t > 0 for t in e)
        and e == sorted(e)
        and row["elapsed_ns"] == e[-1] - e[0] > 0
        and row["drain_ns"] == e[-1] - e[5],
        "epochs",
    )
    warm = restore(row["restore"], prep, e[0])
    numerical(row, prep)
    binds = {binding(x) for x in prep["entries"]}
    need(
        binds == set(map(tuple, row["slot_bindings"]))
        and len(binds) == len(row["slot_bindings"]) == 32,
        "C292 authoritative binding set",
    )
    queue = C["queue"](row, binds)
    primary, spec = {}, {}
    for layer, expert, staged, a, b in row["reads"]:
        need(
            e[0] <= a < b <= e[-1] and staged in (0, 1) and layer in (0, 1),
            "primary clock/read interval",
        )
        if staged:
            need(layer == 1 and expert in OFFERS and expert not in spec, "speculative key")
            spec[expert] = (a, b)
        else:
            need((layer, expert) not in primary, "repeated primary key")
            primary[layer, expert] = (a, b)
    tickets, consumed, stats = ticket_report(row["stage_events"], spec, binds, mode)
    need(row["stage"] == stats, "stage counters differ from event sequence")
    need(
        set(primary) == {(owner, x) for owner, x, _, _ in binds} - {(1, x) for x in consumed},
        "primary sources",
    )
    copies = defaultdict(list)
    for layer, expert, slot, g, c, a, b in row["service"]:
        bind = (layer, expert, slot, g)
        need(
            bind in binds and len(copies[bind]) == c and e[0] <= a <= b <= e[-1],
            "SET destination/role",
        )
        spans = copies[bind]
        earliest = (spans[-1] if spans else primary.get((layer, expert), spec.get(expert)))[1]
        need(a >= earliest, "SET before its own byte source")
        spans.append((a, b))
    need(
        set(copies) == binds
        and all(len(v) == 3 for v in copies.values())
        and row["sets"] == len(row["service"]) == 96,
        "primary SET coverage",
    )
    nr = len(primary) + len(spec)
    need(
        nr == 32 + len(spec) - len(consumed) == row["read_jobs"]
        and len(row["reads"]) == nr
        and row["pread_bytes"] == nr * WINDOW
        and row["slab_hashes"] == (3 * nr if grade == "EXACT" else 0)
        and nr <= 36,
        "byte conservation",
    )
    for expert in consumed:
        # The stage journal's binding validity is observed after the 3rd native SET.
        for k, ev_expert, _, _, _, tick in row["stage_events"]:
            if k == 11 and ev_expert == expert:
                key = next(b for b in binds if b[:2] == (1, expert))
                need(copies[key][-1][1] <= tick * 1000 + 999, "stage commit before final SET")
    waits = defaultdict(list)
    for lnum, a, b in row["wait_intervals_us"]:
        need(lnum in (0, 1) and a <= b, "C294 wait duration")
        waits[lnum].append((a, b))
    need(sum(length(s) * 1000 for s in waits.values()) == row["wait_ns"], "C294 wait sum")
    dense = [s for spans in copies.values() for s in spans]
    peak = C["peak"]([*primary.values(), *spec.values(), *dense])
    need(0 < peak <= 4, "worker limit")
    sources = [(e[1], e[2]), (e[3], e[4])]
    layers = {}
    remaps = {}
    for layer in (0, 1):
        label = f"L{layer}"
        rs = row["remap_ns"][label]
        need(
            len(rs) == 8
            and rs == sorted(rs)
            and sources[layer][0] <= rs[0][0]
            and rs[-1][1] <= sources[layer][1]
            and all(a <= b for a, b in rs)
            and all(rs[i][1] <= rs[i + 1][0] for i in range(7)),
            "remap intervals",
        )
        remaps[layer] = rs
        prim = [v for (owner, _), v in primary.items() if owner == layer]
        st = [v for b, vs in copies.items() if b[0] == layer for v in vs]
        reads = prim + (list(spec.values()) if layer == 1 else [])
        layers[label] = dict(
            official_jobs=sum(b[0] == layer for b in binds),
            primary_reads=len(prim),
            speculative_reads=len(reads) - len(prim),
            sets=len(st),
            read_worker_ns=length(reads),
            read_wall_union_ns=length(merged(reads)),
            set_worker_ns=length(st),
            set_wall_union_ns=length(merged(st)),
            remap_wall_ns=length(rs),
            ggml_wait_us=length(waits[layer]),
        )
    rd0 = [v for (owner, _), v in primary.items() if owner == 0]
    st0 = [v for b, vs in copies.items() if b[0] == 0 for v in vs]
    false_spans = [v for x, v in spec.items() if x != 20]
    return dict(
        grade=grade,
        mode=mode,
        elapsed_ns=row["elapsed_ns"],
        drain_ns=row["drain_ns"],
        restore=warm,
        phase_ns={s: e[i + 1] - e[i] for i, s in enumerate(PHASES)},
        projector_raw_ns=row["producer_ns"],
        layers=layers,
        tickets=tickets,
        queue=queue,
        counters=stats,
        peak_active_workers=peak,
        read_jobs=nr,
        measured_pread_bytes=nr * WINDOW,
        false_pread_bytes=len(false_spans) * WINDOW,
        false_read_worker_ns=length(false_spans),
        false_read_wall_union_ns=length(merged(false_spans)),
        all_offer_overlap=C["overlap"](list(spec.values()), sources[0], remaps[0], rd0, st0),
        false_offer_overlap=C["overlap"](false_spans, sources[0], remaps[0], rd0, st0),
    )


def energy(record):
    first = record.get("host_package_before_spawn")
    last = record.get("host_package_after_exit")
    if first is None or last is None:
        return None
    need(
        first["domain"] == last["domain"] and first["range_uj"] == last["range_uj"] > 0,
        "package meter",
    )
    return (last["energy_uj"] - first["energy_uj"]) % first["range_uj"]


def review(raw, expected, input_dir):
    r = json.loads(sealed(raw / "receipt.json", expected))
    prep = json.loads(sealed(input_dir / "prepare.json", PREP))
    need(
        prep["status"] == "PASS_REAL_TILE_WARM_INPUT" and prep["offers"] == list(OFFERS),
        "preparation receipt",
    )
    for file, digest in prep["file_sha256"].items():
        need(Path(file).name == file, "prepared member")
        sealed(input_dir / file, digest)
    need(
        len(prep["file_sha256"]) == 72
        and len(prep["warm_records"]) == 80
        and len(prep["entries"]) == 32,
        "inputs",
    )
    arms = []
    for i, a in enumerate(r["arms"]):
        need(i < len(ORDER) and (a["grade"], a["mode"]) == ORDER[i], "block order")
        folder = raw / f"{i:02d}-{a['grade']}-{a['mode']}"
        need(a == json.loads((folder / "receipt.json").read_bytes()), "individual receipt")
        for name in ("stdout", "stderr"):
            if name + "_sha256" in a:
                sealed(folder / name, a[name + "_sha256"])
        if a["status"] != "PASS_ARM":
            need(
                r["status"] == "FAIL_PRESERVED" and i == len(r["arms"]) - 1, "failure continuation"
            )
            continue
        need(a["returncode"] == 0, "exit")
        row = json.loads(sealed(folder / "stdout", a["stdout_sha256"]))
        result = analyze(row, *ORDER[i], prep)
        need(
            (a["elapsed_ns"], a["read_jobs"], a["pread_bytes"], a["sets"], a["stage"])
            == (row["elapsed_ns"], row["read_jobs"], row["pread_bytes"], row["sets"], row["stage"]),
            "arm summary",
        )
        result.update(
            stdout_sha256=a["stdout_sha256"],
            stderr_sha256=a["stderr_sha256"],
            process_s=a["observed_process_s"],
            host_package_process_uj=energy(a),
        )
        arms.append(result)
    if r["status"] == "FAIL_PRESERVED":
        return dict(
            status="REPRODUCED_PRESERVED_FAILURE",
            source_sha256=expected,
            passed_arms=arms,
            reason=r.get("reason"),
            decision="INCONCLUSIVE",
            input_sha256=PREP,
        )
    need(
        r["status"] == "PASS_WARM_TILE_FAMILY"
        and len(arms) == 6
        and r["input_sha256"] == PREP
        and r["swap_peak_bytes"] == 0
        and len(r["remaining_pids"]) == 1,
        "complete family",
    )
    ds, verdict = C["outcome"]([a["elapsed_ns"] for a in arms[2:]])
    need(ds == r["paired_saved_ns"] and verdict == r["decision"], "paired sign")
    inventory = raw / "raw" / (r["unit"] + ".start-inventory.jsonl")
    c118 = sealed(inventory, r["c118"]["sha256"]).splitlines()
    need(len(c118) == r["c118"]["sample_count"] and r["c118"]["duration_s"] >= 60, "C118 seal")
    samples = (raw / "samples.jsonl").read_bytes()
    obs = [json.loads(line) for line in samples.splitlines()]
    need(
        len(obs) == r["monitor_samples"] >= 2 and len({a["pid"] for a in r["arms"]}) == 6,
        "child/monitor census",
    )
    need(all(not s["compute_pids"] for s in obs), "unexpected GPU compute")
    return dict(
        status="REPRODUCED_WARM_TILE_FAMILY",
        source_sha256=expected,
        decision=verdict,
        paired_off_minus_on_ns=ds,
        input_sha256=PREP,
        build_sha256=r["build_sha256"],
        binary_sha256=r["binary_sha256"],
        commit=r["commit"],
        tree=r["tree"],
        c55_sha256=r["c55_sha256"],
        c118=r["c118"],
        elapsed_s=r["elapsed_s"],
        resources=dict(
            cgroup_peak_bytes=r["peak_bytes"],
            swap_peak_bytes=r["swap_peak_bytes"],
            monitor_samples=len(obs),
            samples_sha256=hashlib.sha256(samples).hexdigest(),
            max_cpu_c=max(s["thermal"]["cpu_tctl_c"] for s in obs),
            max_nvme_c=max(
                t for s in obs for t in s["thermal"]["nvme_composite_by_sensor"].values()
            ),
            max_gpu_c=max(s["gpu"]["temperature_c"] for s in obs),
            max_gpu_w=max(s["gpu"]["power_w"] for s in obs),
            max_gap_s=max(s["gap_s"] or 0 for s in obs),
        ),
        arms=arms,
        clocks={
            "native": "steady_clock ns, source to end of worker joins",
            "ticket": "steady_clock truncated to microseconds",
            "host_wait": "GGML microsecond durations",
            "producer": "separate CLOCK_MONOTONIC_RAW duration",
            "process": "spawn/poll/exit wall, includes setup, restore and cleanup",
            "energy": "host package from before spawn to after exit if accessible",
        },
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for arg in ("raw", "prepared", "new-output-dir"):
        ap.add_argument("--" + arg, type=Path, required=True)
    ap.add_argument("--sha256", required=True)
    args = ap.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir(mode=0o700, exist_ok=False)
    try:
        receipt = review(args.raw, args.sha256, args.prepared)
    except Exception as exc:
        receipt = {
            "status": "FAIL_REVIEW_PRESERVED",
            "reason": repr(exc),
            "source_sha256": args.sha256,
        }
    with (args.new_output_dir / "receipt.json").open("x") as out:
        json.dump(receipt, out, indent=2, sort_keys=True)
        out.write("\n")
    print(receipt["status"], receipt.get("reason", receipt.get("decision", "")))
    raise SystemExit(int(receipt["status"] == "FAIL_REVIEW_PRESERVED"))
