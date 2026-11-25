"""Seal T1-only publication recency before replaying a fixed bank in C281 T2."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
control = run_path(str(HERE.parent / "t1_bank_capture/score.py"))
src, causal, layout = (control[k] for k in ("src", "causal", "layout"))
need, fd, PAY = src.need, src.fd, control["PAY"]
PACK, K = control["WINDOW"], control["K"]
METHOD = "c65cd87d449c2368efbe0b930f5b4d493abf5819522f3dc14762bfeffcf80812"
REFERENCE = "6c444c8edf073416d539ca07e3ea19797f69e4b28ac881f0bafc76af6e749160"
JOURNAL = "40d2ea8049ccee9213ffc3f317482d67ebbed85a887a933043a3f4e7bd132033"
PHASES = ("call5", "call148", "restore", "decode")
TIERS = ("cpu", "cuda")


def pin_programs():
    for file, pin in (
        (HERE / "protocol.md", METHOD),
        (
            HERE.parent / "t1_bank_capture/score.py",
            "80b62207ba33d121dc24f1e180d7e7a760b0d774bea6e2f33338079602a794fc",
        ),
        (
            HERE.parent / "t1_primary_victim/screen.py",
            "6dd24db84953b9d9f32421d8b8491af73fa9b886256b9412abe4efb19dd10032",
        ),
        (
            HERE.parent / "t1_primary_layout/plan.py",
            "192ef46b7c62473849c269bfa5300547175152b314878d3f487efd93c0a149cf",
        ),
    ):
        need(src.sha(file) == pin, "procedure " + file.name)


def offers(rows):
    components = defaultdict(lambda: {"READ": set(), "SET": set()})
    weights = {(r.layer, r.component): (r.fd, r.a, r.b) for r in rows if r.kind == 8}
    events = []
    counters = defaultdict(Counter)
    for r in rows:
        kind = fd.NAMES[r.kind]
        need(kind != "LOAD_FAIL", "failed worker load")
        if kind not in ("READ", "SET", "PUBLISH"):
            continue
        key = fd.identity(r)
        tier = control["tier"]((r.layer, r.expert))
        c = counters[tier]
        if kind == "PUBLISH":
            c["published"] += 1
            if components.pop(key, {}) == {"READ": {0, 1, 2}, "SET": {0, 1, 2}}:
                events.append(((r.layer, r.expert), r.call))
            else:
                need(r.call == 0, "publication without three staging components")
                c["incomplete_inherited"] += 1
            continue
        need(
            r.error == 0 and r.component in (0, 1, 2) and r.component not in components[key][kind],
            "component",
        )
        owner, base, size = weights[r.layer, r.component]
        need(r.fd == owner and size == PAY // 3, "weight/FD")
        if kind == "READ":
            offset = base + size * r.expert
            head = offset % 4096
            window = (head + size + 4095) // 4096 * 4096
            need(
                r.a == offset - head and r.b == window and head + size <= r.c <= window,
                "read return",
            )
            c["observed_fd_requested_bytes"] += r.b
            c["observed_fd_returned_bytes"] += r.c
        else:
            need(
                r.a == size
                and r.b == size * r.slot
                and (r.component in components[key]["READ"] or r.call == 0),
                "staging order",
            )
            c["observed_set_bytes"] += r.a
        components[key][kind].add(r.component)
    need(not components, "pending transport at T1 seal")
    return events, counters


def prepare(part):
    rows = control["prefix_records"](part)
    need(
        len(rows) == 47303
        and src.audit.record_digest(rows)
        == "7c0ef30ca09fca94e1f8be7c178f7a43ab1a9a9f3e9a1fe2e0da792b4fa6a3b2",
        "T1 seal",
    )
    slots, fifo, victims = src.audit.state_before(rows)
    need(not fifo and all(s in (0, 2) and not c for _, _, s, c in slots), "drained T1")
    primary = {(i // 40, e) for i, (e, _, s, _) in enumerate(slots) if s == 2}
    feed, t1 = offers(rows)
    keys, indexes, stats, washout = control["maintain"](feed, K)
    victim_keys, _, _, _ = control["maintain"]([(k,) for k in victims], K)
    need(washout is not None and len(keys) == len(victim_keys) == K, "bank not washed out")
    for tier in TIERS:
        c = t1[tier]
        c.update(stats[tier])
        installs = sum(control["tier"](feed[i][0]) == tier for i in indexes)
        need(installs == c["first_install"] + c["reinstall"], "installation")
        c["installations"] = installs
        c["distinct_offers"] = len({k for k, _ in feed if control["tier"](k) == tier})
        c["logical_install_payload_bytes"] = installs * PAY
        c["pack_imputed_pread_bytes_for_complete_offers"] = c["offers"] * PACK
        c["eager_host_copy_all_offers_bytes"] = c["offers"] * PAY

    def intersections(bank):
        return {
            label: src.audit.per_tier(group)
            for label, group in (
                ("retained", set(bank)),
                ("already_primary", set(bank) & primary),
                ("outside_primary", set(bank) - primary),
            )
        }

    return {
        "selection": {"published": keys, "victims": victim_keys},
        "t1": {
            "by_destination_tier": t1,
            "washout_offer": washout + 1,
            "washout_call": feed[washout][1],
            "before_t2": {"source": intersections(keys), "victims": intersections(victim_keys)},
            "common_bank_keys": src.audit.per_tier(set(keys) & set(victim_keys)),
            "ordered_hash": {
                "source": src.audit.digest(keys),
                "victims": src.audit.digest(victim_keys),
            },
        },
    }


def t2(part):
    root = part / src.ARM
    src.pinned(root / "receipt.json", src.FAIL)
    rows, header = fd.read_journal(root / "raw/events.pfj")
    need(header["journal_sha256"] == JOURNAL, "PFJ1 seal")
    n = 47303
    prefix = rows[:n]
    need(
        src.audit.record_digest(prefix)
        == "7c0ef30ca09fca94e1f8be7c178f7a43ab1a9a9f3e9a1fe2e0da792b4fa6a3b2",
        "same prefix",
    )
    slots, _, _ = src.audit.state_before(prefix)
    shift = 73
    grade = src.audit.conservation(rows, header, None, shift + 1)
    calls = grade["calls"][shift:]
    expected = [(5, [2044, 2048], [5]), (148, [2049, 2196], [32, 32, 32, 32, 20])]
    expected += [(1, [p, p], [1]) for p in range(2197, 2243)]
    need([(c["tokens"], c["positions"], c["tiles"]) for c in calls] == expected, "T2 geometry")
    need(rows[n].kind == 1 and rows[n].call == shift + 1, "T2 entry")
    local = src.local_slots(prefix, slots) + [
        r._replace(call=r.call - shift if r.call > 0 else r.call) for r in rows[n:]
    ]
    end = next(i for i, r in enumerate(local) if r.kind == 2 and r.call == 2)
    entry = next(i for i, r in enumerate(local) if r.kind == 1 and r.call == 3)
    need(entry == end + 1 and local[end].b == local[end].c == 0, "first decode cut")
    meta = {(r.layer, r.component): (r.a, r.b) for r in prefix if r.kind == 8}
    need(len(meta) == 108 and all(n == PAY // 3 for _, n in meta.values()), "weights")
    return causal["inputs"](local), meta


def gguf_bytes(key, meta):
    layer, expert = key
    total = 0
    for i in range(3):
        start, size = meta[layer, i]
        offset = start + size * expert
        total += ((offset % 4096 + size + 4095) // 4096) * 4096
    return total


def replay(work, meta, bank, prefer, budgets):
    initial, final, waves = work
    pools = [causal["Pool"](p) for p in initial]
    ledger = {phase: {t: Counter() for t in TIERS} for phase in PHASES}
    counts = defaultdict(Counter)

    def add(phase, key, origin):
        c = ledger[phase][control["tier"](key)]
        c[origin] += 1
        if origin != "primary":
            c["destination_payload"] += PAY
        if origin == "disk":
            c["gguf_fd_bytes"] += gguf_bytes(key, meta)
            c["pack_fd_bytes"] += PACK

    first_decode = True
    for tick, (call, layer, demand) in enumerate(waves, 1):
        if call > 2 and first_decode:
            for i, pool in enumerate(pools):
                for e in final[i]:
                    if e >= 0 and e not in pool.slots:
                        add("restore", (i, e), "ram" if (i, e) in bank else "disk")
                pool.restore(i, final[i], bank, tick, counts["restore"])
            first_decode = False
        phase = "call5" if call == 1 else "call148" if call == 2 else "decode"
        pool = pools[layer]
        origin = layout["origins"](pool, layer, demand, bank)
        for e, s in zip(demand, origin, strict=True):
            add(phase, (layer, e), s)
        pool.wave(layer, demand, bank, prefer, tick, counts[phase])
    for phase, tiers in ledger.items():
        for origin in ("disk", "ram", "primary"):
            need(
                sum(c[origin] for c in tiers.values()) == counts[phase][origin],
                "charge conservation",
            )
    pre = sum((c for phase in PHASES[:3] for c in ledger[phase].values()), Counter())
    dec = counts["decode"]["disk"]
    floor = causal["compulsory"](initial, final, waves, bank, True)
    need(floor <= pre["disk"], "first miss floor")
    return {
        "phases_by_destination": ledger,
        "prefill_including_restore": pre,
        "decode_disk": dec,
        "compulsory_disk_with_restore": floor,
        "floor_payload_bytes": floor * PAY,
        "scenario": {
            q: {
                "payload_volume_pass": pre["disk"] * PAY <= b,
                "gguf_volume_pass": pre["gguf_fd_bytes"] <= b,
                "pack_volume_pass": pre["pack_fd_bytes"] <= b,
                "decode_pass": dec <= 872,
                "joint_payload_pass": pre["disk"] * PAY <= b and dec <= 872,
                "floor_excess_bytes": floor * PAY - b,
            }
            for q, b in budgets.items()
        },
    }


def score(part, selected, seal_hash):
    seal = src.pinned(selected, seal_hash)
    need(seal == json.loads(json.dumps(prepare(part))), "causal selection before T2")
    published = set(map(tuple, seal["selection"]["published"]))
    victims = set(map(tuple, seal["selection"]["victims"]))
    ref = src.pinned(HERE.parent / "t1_bank_capture/evidence/receipt.json", REFERENCE)
    need(ref["journal_sha256"] == JOURNAL, "control identity")
    work, meta = t2(part)
    cases = (
        ("lru_off", set(), False, "lru"),
        ("lru_victims", victims, False, "lru_ram"),
        ("priority_victims", victims, True, "evict_backed_first"),
        ("lru_source", published, False, None),
        ("priority_source", published, True, None),
    )
    arms = {}
    for name, bank, prefer, existing in cases:
        arm = arms[name] = replay(work, meta, bank, prefer, ref["budgets"])
        if existing:
            for phase, tiers in arm["phases_by_destination"].items():
                old = ref["t2"][existing]["phases"]["eager"][phase]
                for source in ("primary", "ram", "disk"):
                    for t in TIERS:
                        need(
                            old.get(source + "_" + t, 0) == tiers[t][source],
                            "control phase/tier count",
                        )
                for k in ("gguf_fd_bytes", "pack_fd_bytes"):
                    need(
                        old.get(k, 0) == sum(c[k] for c in tiers.values()), "control FD byte count"
                    )
    source_results = [arms[n]["scenario"]["47"] for n in ("lru_source", "priority_source")]
    floor_fails = all(r["floor_excess_bytes"] > 0 for r in source_results)
    return {
        "status": "GO_FIXTURE_ONLY"
        if any(r["joint_payload_pass"] for r in source_results)
        else "NO_GO_NOMINAL_FLOOR"
        if floor_fails
        else "NO_GO_TESTED_POLICIES",
        "time_decision": "INCONCLUSIVE",
        "protocol_sha256": METHOD,
        "source_sha256": src.sha(Path(__file__)),
        "selection_file_sha256": seal_hash,
        "prior_sha256": REFERENCE,
        "journal_sha256": JOURNAL,
        "t1": seal["t1"],
        "t2": arms,
        "conditional_volume_budgets": ref["budgets"],
        "observed_r0_disk": {"prefill": 1263, "decode": 1091},
        "bank_payload_bytes": K * PAY,
        "record_window": PACK,
        "bank_extra_bytes": ref["extra_bytes"],
        "headroom_at_observed_peak": ref["headroom_bytes"],
        "new_forwards": 0,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("prepare", "score"))
    p.add_argument("--part", required=True, type=Path)
    p.add_argument("--new-output-dir", required=True, type=Path)
    p.add_argument("--selection", type=Path)
    p.add_argument("--selection-sha256")
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        pin_programs()
        if a.action == "prepare":
            result, name = prepare(a.part), "selection.json"
        else:
            need(
                a.selection and a.selection_sha256,
                "private selection and independent hash required",
            )
            result, name = score(a.part, a.selection, a.selection_sha256), "receipt.json"
    except (OSError, ValueError, KeyError, IndexError, StopIteration) as exc:
        src.possible.save(
            a.new_output_dir / "receipt.json",
            {
                "status": "NOT_RUN_RAW_REQUIRED"
                if isinstance(exc, FileNotFoundError)
                else "FAIL_PRESERVED",
                "reason": str(exc),
            },
        )
        raise
    temp = a.new_output_dir / "output.tmp"
    src.possible.save(temp, result)
    temp.rename(a.new_output_dir / name)


if __name__ == "__main__":
    main()
