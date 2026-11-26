"""Price acquisition of the same T1 victim bank now, at the cut, or on first use."""

import argparse
import hashlib
import json
import os
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
layout = run_path(str(HERE.parent / "t1_primary_layout/plan.py"))
causal, src = layout["causal"], layout["src"]
need = src.need
PAY = 13_219_200
WINDOW = 13_221_888
K = 353
METHOD = "14aa0cb25a4becbb18b7cf798d13f9fa684e844f4a1f08e6e0e0fb79bd066850"
LOCAL = "eb08c93c08201a8074a996a2f898505a452be38f20c03b345df77f9a7a04638a"
SEAL = "d5321a870115d479ea5d53016a1796bda52dff0d343984d9aa05e92676a384d4"


def tier(key):
    return "cpu" if key[0] < 25 else "cuda"


def minimum_bytes_per_second(payload, nanos):
    need(nanos > 0, "zero time")
    return (payload * 10**9 + nanos - 1) // nanos


def maintain(offers, k, initial=()):
    order = OrderedDict.fromkeys(initial)
    seen = set()
    counters = defaultdict(Counter)
    installs = []
    washout = None
    for idx, (key, *_) in enumerate(offers):
        t = tier(key)
        c = counters[t]
        c["offers"] += 1
        if key in order:
            c["mru_noop" if next(reversed(order)) == key else "promotion"] += 1
            order.move_to_end(key)
        else:
            if len(order) == k:
                discard = order.popitem(last=False)[0]
                counters[tier(discard)]["discards"] += 1
            order[key] = None
            c["reinstall" if key in seen else "first_install"] += 1
            installs.append(idx)
        seen.add(key)
        if washout is None and len(seen) == k:
            washout = idx
    return list(order), installs, counters, washout


def prefix_records(part):
    files = src.manifest(part)
    root = part / src.ARM
    path = root / "before-t2.json"
    cut = src.pinned(path, files[src.ARM + "/before-t2.json"]["sha256"])
    with (root / "raw/events.pfj").open("rb") as f:
        f.seek(src.fd.HEADER.size)
        data = f.read(cut["bytes"])
    need(
        len(data) == cut["records"] * src.fd.RECORD.size
        and hashlib.sha256(data).hexdigest() == cut["sha256"],
        "immutable pre-POST prefix",
    )
    return [src.fd.Row(*r) for r in src.fd.RECORD.iter_unpack(data)]


def price_prefix(rows, prefix, k):
    slots = {}
    offers = []
    writes = {}
    calls = {}
    for r in rows:
        g = src.fd.identity(r)
        if r.kind == 1:
            calls[r.call] = [r.ns, None]
        elif r.kind == 2:
            calls[r.call][1] = r.ns
        elif r.kind == 5:
            slots[r.layer, r.slot] = (r.expert, r.gen, r.a)
        elif r.kind == 11:
            old, gen, state = slots[r.layer, r.slot]
            need(old == r.a and gen + 1 == r.gen and state in (0, 2), "valid victim")
            if state == 2:
                offers.append(((r.layer, old), r.ns, r.call, g))
            slots[r.layer, r.slot] = (r.expert, r.gen, 1)
        elif r.kind == 16:
            if g not in writes:
                writes[g] = r.begin
            else:
                writes[g] = min(writes[g], r.begin)
        elif r.kind == 17:
            need(slots[r.layer, r.slot] == (r.expert, r.gen, 1), "published generation")
            slots[r.layer, r.slot] = (r.expert, r.gen, 2)
    expected = prefix["capacities"][str(k)]
    keys, install, stats, wash = maintain(offers, k)
    need(
        src.audit.digest(keys) == expected["ordered_keys_sha256"] and wash is not None,
        "bank washout",
    )
    first = list(dict.fromkeys(e[0] for e in offers))[:k]
    lowkeys, low, _, _ = maintain(offers, k, first)
    need(lowkeys == keys, "same state after washout")
    wall = calls[max(calls)][1] - calls[min(calls)][0]
    by_tier = {}
    for t in ("cpu", "cuda"):
        actual = [offers[i] for i in install if tier(offers[i][0]) == t]
        minimum = sum(tier(offers[i][0]) == t for i in low)
        need(
            len(actual) == expected["cold_start_copies_by_tier"][t]
            and minimum == expected["minimum_copies_over_unknown_start_by_tier"][t],
            "prior prefix proof",
        )
        intervals = []
        call_count = Counter()
        for _, start, n, g in actual:
            if g not in writes:
                continue
            end = writes[g]
            need(end > start, "first replacement SET window")
            intervals.append(end - start)
            a, b = calls[n]
            if a <= start < end <= b:
                call_count[n] += 1
        rates = [
            minimum_bytes_per_second(PAY * v, calls[c][1] - calls[c][0])
            for c, v in call_count.items()
        ]
        by_tier[t] = dict(
            offers=stats[t]["offers"],
            unique=len({key for key, *_ in offers if tier(key) == t}),
            installed=len(actual),
            installed_min=minimum,
            bytes_min=minimum * PAY,
            bytes_cold=len(actual) * PAY,
            retained=sum(tier(key) == t for key in keys),
            counters=stats[t],
            suffix_minimum_Bps_cold=minimum_bytes_per_second(len(actual) * PAY, wall),
            exact_windows=len(intervals),
            censored=len(actual) - len(intervals),
            shortest_window_ns=min(intervals, default=None),
            peak_individual_minimum_Bps=max(
                (minimum_bytes_per_second(PAY, n) for n in intervals), default=0
            ),
            count_contained_in_call=sum(call_count.values()),
            max_call_minimum_Bps=max(rates, default=0),
        )
    need(
        sum(v["offers"] for v in by_tier.values()) == prefix["victim_offers"]
        and sum(v["unique"] for v in by_tier.values()) == prefix["distinct_victim_keys"],
        "offers",
    )
    return dict(
        positions=[prefix["first_position"], prefix["last_position"]],
        calls=len(calls),
        wall_ns=wall,
        washout_offer=wash + 1,
        washout_call=offers[wash][2],
        washout_offset_ns=offers[wash][1] - calls[min(calls)][0],
        by_tier=by_tier,
    )


def materialize(phase, requests, ready, ledger, sizes):
    """At group completion each first demand (disk) has one reusable READY entry."""
    check_keys = set()
    for key, origin in requests:
        need(key not in check_keys, "duplicate consumer within a cohort")
        check_keys.add(key)
        event = "first_disk_for_bank" if origin == "ram" and key not in ready else origin
        dest = tier(key)
        for role, source_ in (("eager", origin), ("lazy", event)):
            c = ledger[role][phase]
            c[source_] += 1
            c[source_ + "_" + dest] += 1
            if source_ in ("disk", "first_disk_for_bank"):
                c["gguf_fd_bytes"] += sizes(key)
                c["pack_fd_bytes"] += WINDOW
        if event == "first_disk_for_bank":
            ledger["lazy"][phase]["bank_write_bytes_" + dest] += PAY
    ready.update(k for k, origin in requests if origin == "ram")


def replay_t2(rows, bank, name, control, sizes):
    initial, required, waves = causal["inputs"](rows)
    pools = [causal["Pool"](v) for v in initial]
    prices = defaultdict(Counter)
    ledger = {label: defaultdict(Counter) for label in ("eager", "lazy")}
    entered = False
    ready = set()
    nbank = bank if name != "lru" else set()
    for tick, (call, layer, demand) in enumerate(waves, 1):
        if call > 2 and not entered:
            for i, p in enumerate(pools):
                active = set(p.slots)
                misses = [
                    ((i, e), "ram" if (i, e) in nbank else "disk")
                    for e in required[i]
                    if e >= 0 and e not in active
                ]
                materialize("restore", misses, ready, ledger, sizes)
                p.restore(i, required[i], nbank, tick, prices["restore"])
            entered = True
        p = pools[layer]
        origins = layout["origins"](p, layer, demand, nbank)
        phase = "call5" if call == 1 else "call148" if call == 2 else "decode"
        materialize(
            phase,
            [((layer, e), s) for e, s in zip(demand, origins, strict=True)],
            ready,
            ledger,
            sizes,
        )
        p.wave(
            layer,
            demand,
            nbank,
            name == "evict_backed_first",
            tick,
            prices["prefill" if call <= 2 else "decode"],
        )
    for p in ("prefill", "restore", "decode"):
        need(prices[p] == control["restore"][p], "primary replay exact conservation")
        tel = (
            ledger["eager"]["call5"] + ledger["eager"]["call148"]
            if p == "prefill"
            else ledger["eager"][p]
        )
        need(all(tel[k] == v for k, v in prices[p].items()), "bank counts")
    need(
        len(ready) == sum(q["first_disk_for_bank"] for q in ledger["lazy"].values())
        and ready <= nbank,
        "unique lazy first copy",
    )
    return dict(
        phases=ledger,
        ready=len(ready),
        never_used=len(nbank - ready),
        ready_by_tier=src.audit.per_tier(ready),
        maximum_live_payload=len(ready) * PAY,
    )


def run(args):
    check = src.need
    check(src.sha(HERE / "protocol.md") == METHOD, "procedure")
    sealed = src.pinned(args.prepared_dir / "receipt.json", SEAL)
    prep = src.pinned(args.prepared_dir / "selection.json", sealed["selection_sha256"])
    check(prep == json.loads(json.dumps(src.prepared(args.part))), "before-POST eligibility")
    prefix = prep["prefix"]
    warm = set(map(tuple, prefix["capacities"]["353"]["ordered_keys"]))
    t1 = price_prefix(prefix_records(args.part), prefix, K)
    local = src.pinned(args.local_dir / "receipt.json", LOCAL)
    ctl = src.pinned(HERE.parent / "t1_primary_victim/evidence/causal.json", layout["CAUSAL"])
    s = src.load_inputs(args.part, args.model, args.inventory, args.prepared_dir)
    need(
        s.journal == local["journal_sha256"] == ctl["journal_sha256"] and len(warm) == K, "same T2"
    )

    def size(k):
        layer, e = k
        total = 0
        for i in range(3):
            base, n = s.meta[layer, i]
            pos = base + n * e
            total += ((pos % 4096 + n + 4095) // 4096) * 4096
        return total

    budgets = local["results"]["current"]["budgets"]
    policies = {}
    for name in ("lru", "lru_ram", "evict_backed_first"):
        r = replay_t2(s.rows, warm, name, ctl["arms"][name], size)
        prefix_size = sum(size(key) for key in warm) if name != "lru" else 0
        setup_pack = len(warm) * WINDOW if name != "lru" else 0
        prices = {}
        for method in ("A_cold", "B_at_cut", "C_lazy"):
            vals = r["phases"]["lazy" if method == "C_lazy" else "eager"]
            pre = sum((vals[p] for p in ("call5", "call148", "restore")), Counter())
            dec = vals["decode"]
            extra_gguf = prefix_size if method == "B_at_cut" else 0
            extra_pack = setup_pack if method == "B_at_cut" else 0
            n = pre["disk"] + pre["first_disk_for_bank"]
            d = dec["disk"] + dec["first_disk_for_bank"]
            prices[method] = dict(
                prefill_origin_loads=n,
                decode_origin_loads=d,
                charged_prefill_gguf_fd_bytes=pre["gguf_fd_bytes"] + extra_gguf,
                charged_prefill_pack_fd_bytes=pre["pack_fd_bytes"] + extra_pack,
                at_cut_gguf_fd_bytes=extra_gguf,
                at_cut_pack_fd_bytes=extra_pack,
                decode_gguf_fd_bytes=dec["gguf_fd_bytes"],
                decode_pack_fd_bytes=dec["pack_fd_bytes"],
                decode_gate=d <= 872,
                volume_gate_by_layout={
                    ly: {q: pre[ly + "_fd_bytes"] + v <= maximum for q, maximum in budgets.items()}
                    for ly, v in (("gguf", extra_gguf), ("pack", extra_pack))
                },
            )
        r["prices"] = prices
        policies[name] = r
    extra = src.admit.t2.host.additional(K)
    return dict(
        status="PASS_BANK_CONSTRUCTION_BYTE_ACCOUNTING",
        time_decision="INCONCLUSIVE_UNMEASURED_COPIES",
        method_sha256=METHOD,
        program_sha256=src.sha(Path(__file__)),
        local=LOCAL,
        seal=SEAL,
        causal_control_sha256=layout["CAUSAL"],
        journal_sha256=s.journal,
        payload_bytes=PAY,
        capacity=K,
        extra_bytes=extra,
        headroom_bytes=s.memory,
        remaining_bytes=s.memory - extra,
        budgets=budgets,
        t1=t1,
        t2=policies,
        model_forwards=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("part", "model", "inventory", "prepared-dir", "local-dir", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir(mode=0o700)
    try:
        r = run(args)
    except Exception as exc:
        r = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    src.possible.save(args.new_output_dir / "receipt.json", r)
    print(r["status"])
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
