"""Join packed transport, one-layer authority and both clocks of each natural T2."""

import argparse
import hashlib
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
PREFILL = HERE.parent / "screen.py"
L = run_path(str(PREFILL))
C, Q, REL = L["COST"], L["Q"], L["COST"]["RELEASE"]
check, canonical, size = L["check"], L["canonical"], L["SIZE"]
NS = 10**9
METHOD = "99853d95bb353e9ff45d090b9fe4248d5c4485b9378f1a893d84013394100efe"
PARENT_CODE = "ead509600e5d942555af63d74f4faf372a867e9e7364b61cd6585cdbe92481f3"
PARENT_OUTPUT = "cb100940b5b5eeae519b534b54667ce4f5147cf8f006d86e2ab8ed26fdfa624a"
PHASES = ("prefill", "decode_first", "decode_tail")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def strict(test, reason):
    if not test:
        raise ValueError("INCONCLUSIVE " + reason)


def assert_cut(waves, lower, upper):
    for w in waves:
        if w.site[0] <= 46:
            strict(w.end <= lower, "early callback reaches uncertain SSE boundary")
        else:
            strict(w.start >= upper, "tail callback crosses first final")


def resources(total, tasks, rate, sets):
    early = L["early_capacity"](tasks, rate)
    check(0 <= early <= total * NS and sets >= 0, "invalid resource floor")
    missing = total * NS - early
    network = missing // rate
    return early, network, max(network, sets)


def budget(first, decode, callbacks, residual):
    p, e, t = [callbacks[i] - residual[i] for i in range(3)]
    first_floor = first - p - e
    decode_floor = decode - e - t
    check(first_floor >= 0 and decode_floor > 0, "invalid remaining clock")
    f, d = 10 * NS - first_floor, 47 * NS // 6 - decode_floor
    return {
        "first_floor_ns": first_floor,
        "decode_floor_ns": decode_floor,
        "first_margin_ns": f,
        "decode_margin_ns": d,
        "shared_extra_ceiling_ns": min(f, d),
        "joint": "HEADROOM_ONLY" if min(f, d) >= 0 else "NO_GO_FIXED_SCENARIO",
    }


def decode_markers(rows, host):
    # The predecessor's prefill marker rejects calls >2. Keep its window and contraction rules.
    begins, ends, ranks, tiles = {}, {}, defaultdict(list), {}
    for r in rows:
        if r.call <= 2:
            continue
        cell = r.call, r.tile, r.layer
        if r.kind == 3:
            check(cell[:2] not in tiles and r.a == 1, "decode tile span")
            tiles[cell[:2]] = r.ns
        elif r.kind == 9:
            check(cell not in begins and r.wave in (0, -1), "duplicate decode remap")
            begins[cell] = r.ns
        elif r.kind == 23:
            check(cell not in ends, "duplicate decode return")
            ends[cell] = r.ns
        elif r.kind == 27:
            check(r.b == 0 and r.wave in (0, -1), "decode rank row")
            ranks[cell].append(r.ns)
    cells = {(c, 1, layer) for c in range(3, 49) for layer in range(36)}
    check(begins.keys() == ends.keys() == ranks.keys() == cells, "46 complete decode graphs")
    for cell in cells:
        c, t, layer = cell
        check(len(ranks[cell]) == 1 and begins[cell] <= ranks[cell][0] <= ends[cell], "authority")
        if layer:
            check(ends[c, t, layer - 1] <= begins[cell], "layer order")
    spans = [(a, b) for c, a, b in host["callback_spans"] if c > 2]
    check(len(spans) == len(cells), "decode callbacks")
    return begins, ends, ranks, tiles, spans


def population(rows, waves, host, bank, tiers):
    routes = Q["L"]["ranks"](rows, 1)
    pre = Q["L"]["strict_keys"](rows, host)
    first_gen = REL["scopes"](rows, host)[3]
    queue, set_time = defaultdict(list), defaultdict(list)
    for r in rows:
        if r.kind == 12:
            queue[C["key"](r)].append((r.a, C["origin"](r)))
        elif r.kind == 16:
            set_time[C["key"](r)].append(r.ns - r.begin)
    volume, counters, physical = Counter(), defaultdict(Counter), []
    set_work = Counter()
    coverage = Counter()
    for w in waves:
        c, tile, layer, _ = w.site
        ph = C["phase"](c)
        charged = w.reserved
        if c > 2:
            rank = set(routes[c - 1, tile, layer, 0])
            check(len(rank) == 4, "decode top four")
            strict(all(k[3] in rank for k in charged), "reservation absent from target ranks")
            strict(w.reserved == set(w.required_service), "decode generation not demanded in site")
        else:
            charged = {
                k
                for k in w.required_service
                if pre.get(C["expert"](k)) == w.site and first_gen[C["expert"](k)] == k
            }
        coverage[ph, "all"] += len(w.reserved)
        coverage[ph, "charged"] += len(charged)
        prices = []
        for k in sorted(charged):
            strict(queue[k] == [(0, w.site)], "ambiguous demand enqueue")
            check(len(set_time[k]) == 3 and min(set_time[k]) >= 0, "three SETs")
            prices.append(sum(set_time[k]))
            hit = C["expert"](k) in bank
            counters[ph][tiers[layer] + ("_bank" if hit else "_pack")] += 1
            volume[w.site] += int(not hit)
            if c > 2:
                physical.append([w.site, k, hit])
        set_work[c] += REL["four_lanes"](prices)
        check(REL["four_lanes"](prices) <= w.end - w.start, "SET floor outside remap")
    check(coverage["prefill", "charged"] == len(pre) == 567, "prefill population")
    strict(sum(coverage[ph, "charged"] for ph in PHASES[1:]) == 1091, "decode coverage")
    return (
        volume,
        set_work,
        {
            ph: dict(
                counters[ph], reservations=coverage[ph, "all"], charged=coverage[ph, "charged"]
            )
            for ph in PHASES
        },
        sha(canonical(physical)),
    )


def price(volume, work, marks, callbacks, first, decode, horizon, release, width, rate):
    tasks, total = defaultdict(list), Counter()
    shrink = [L["contracted"](m[-1]) for m in marks]
    for site, n in volume.items():
        if not n:
            continue
        c = site[0]
        total[c] += n * size
        z = int(c > 2)
        if horizon:
            windows = L["windows"](site, marks[z], horizon, release)
            for a, b, count in L["batches"](windows, n, width):
                tasks[c].append((shrink[z](a), shrink[z](b), count * size))
    info = {ph: Counter() for ph in PHASES}
    for c in range(1, 49):
        early, net, joint = resources(total[c], tasks[c], rate, work[c])
        s = info[C["phase"](c)]
        s["early_byte_ns"] += early
        s["network_ns"] += net
        s["set_ns"] += work[c]
        s["network_or_set_ns"] += joint
        s["pack_bytes"] += total[c]
    for s in info.values():
        s["early_bytes_floor"] = s.pop("early_byte_ns") // NS
    return {
        "phases": info,
        "free_set": budget(first, decode, callbacks, [info[p]["network_ns"] for p in PHASES]),
        "priced_set": budget(
            first, decode, callbacks, [info[p]["network_or_set_ns"] for p in PHASES]
        ),
    }


def assess(root, receipt, rows, tiers, bank, pref):
    host = C["NATIVE"]["host_trace"](rows)
    cut = C["CLIENT"]["inspect"](root / "ON", receipt, host["calls"])
    check((cut["sample_number"], cut["sample_call"]) == (45, 46), "first final return")
    high = host["calls"][45]["return_ns"] + cut["last_relevant_return_to_first_final_ns"]
    low = high - abs(cut["first_frame_minus_metric_ns"]) - 2
    waves, _ = C["timeline"](rows)
    check(
        [(w.site[0], w.start, w.end) for w in waves] == host["callback_spans"]
        and all(a.end <= b.start for a, b in zip(waves, waves[1:], strict=False)),
        "shared callback clock",
    )
    assert_cut(waves, low, high)
    volume, work, pop, seal = population(rows, waves, host, bank, tiers)
    marks = [L["markers"](rows, host), decode_markers(rows, host)]
    callback_time = Counter()
    for c, a, b in host["callback_spans"]:
        callback_time[C["phase"](c)] += b - a
    check(callback_time["prefill"] == pref["all_prefill_callback_ns"], "same prefill clock")
    first, decode = pref["first_final_ns"], pref["decode_ns"]
    windows = pref["banks"]["prefill"]["windows"]
    cases = []
    for h, release, width in [
        (0, "none", "none"),
        *(
            (1, r, w)
            for r in ("earliest_outer", "ranks_observed")
            for w in ("four_per_target", "unlimited")
        ),
    ]:
        for rate in L["RATES"]:
            score = price(
                volume,
                work,
                marks,
                [callback_time[p] for p in PHASES],
                first,
                decode,
                h,
                release,
                width,
                rate,
            )
            if h:
                previous = next(
                    row
                    for row in windows
                    if (row["horizon"], row["release"], row["width"]) == (h, release, width)
                )
                point = next(v for v in previous["limits"] if v["bytes_per_s"] == rate)
                p = score["phases"]["prefill"]
                check(
                    point["contracted_early_bytes_floor"] == p["early_bytes_floor"]
                    and 0 <= point["residual_extra_wall_floor_ns"] - p["network_ns"] <= 1,
                    "different release or prefill anchors",
                )
            cases.append(dict(score, horizon=h, release=release, width=width, bytes_per_s=rate))
    return {
        "baseline_first_ns": first,
        "baseline_decode_ns": decode,
        "callback_ns": callback_time,
        "sample_number": 45,
        "sample_call": 46,
        "return_to_first_final_ns": cut["last_relevant_return_to_first_final_ns"],
        "population": pop,
        "decode_generation_site_bank_sha256": seal,
        "handoff": host["first_decode"],
        "choices": cases,
    }


def run(archive, backend):
    check(
        L["digest"](HERE / "protocol.md") == METHOD and L["digest"](PREFILL) == PARENT_CODE,
        "frozen scope",
    )
    pref = L["run"](archive, backend)
    check(sha(canonical(pref)) == PARENT_OUTPUT, "prefill reproduction")
    refs = C["SOURCES"]
    roots = {k: archive / ("part-" + k[1:]) / v[0] for k, v in refs.items()}
    root = roots["P106"]
    source, rows, tiers, _ = Q["read_new"](root, refs["P106"][1])
    bank = set(map(tuple, source["banks"]["prefill"]["ordered_keys"]))
    check(len(bank) == 353, "frequency bank")
    arm = L["pinned"](root / "family.json", refs["P106"][1])["arms"]["ON"]["arm"]
    p106 = assess(
        root,
        L["pinned"](root / "ON/receipt.json", arm["receipt_sha256"]),
        rows,
        tiers,
        bank,
        pref["P106"],
    )
    del rows
    root = roots["P97"]
    _, _, receipt, audit = C["CHAIN"]["chain"](root, refs["P97"][1])
    rows, header = L["T"]["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
    check(audit["header"] == header, "P97 journal")
    p97 = assess(root, receipt, rows, tiers, bank, pref["P97"])
    for k in ("handoff", "decode_generation_site_bank_sha256", "population"):
        check(p97[k] == p106[k], "different cross-process " + k)
    return {
        "status": "REPRODUCED_TWO_PHASE_PACK_BUDGET",
        "code_sha256": L["digest"](Path(__file__)),
        "protocol_sha256": METHOD,
        "prefill_receipt_sha256": PARENT_OUTPUT,
        "prefill_code_sha256": PARENT_CODE,
        "source": pref["T1"],
        "P97": p97,
        "P106": p106,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "backend", "new-output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(args.archive, args.backend)
    except (ValueError, OSError, KeyError, StopIteration) as exc:
        result = {
            "status": "INCONCLUSIVE" if str(exc).startswith("INCONCLUSIVE") else "FAIL_PRESERVED",
            "error": type(exc).__name__,
            "reason": str(exc),
        }
    (args.new_output_dir / "receipt.json").write_bytes(canonical(result))
    print(result["status"])
    raise SystemExit(int(result["status"] != "REPRODUCED_TWO_PHASE_PACK_BUDGET"))
