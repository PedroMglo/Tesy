"""Same-tile, two-layer price ceiling for strict packed first-use jobs across CPU and CUDA."""

import argparse
import heapq
import json
from bisect import bisect_right
from collections import Counter, defaultdict
from decimal import Decimal
from itertools import accumulate
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
NAT = HERE.parents[1]
COST = run_path(str(NAT / "prefill_retention/request_cost/score.py"))
Q, T = COST["Q"], COST["T"]
check, digest, pinned = Q["check"], Q["digest"], Q["pinned"]
SIZE = COST["RELEASE"]["PAYLOAD"]
NS = 10**9
METHOD = "8a5347e2ad6e9a78a315b56ebb97609534cc4105dd6bb2f60e5b8bc39ede258c"
ARITHMETIC = "71187a229111ccbf86c0482d5150cb0a851c554180ccb725c10acfafa8a66fca"
PRIORS = "04765c8b016a1e69ce61ba150e985bed8c64a6d8e11d58bd7fb9f87768186dac"
SOURCES = {
    "src/models/openai-moe.cpp": "239407aaa98f8b65eb280e4423588ba7cefc520371811b9c47d7457fc1f469d4",
    "src/llama-graph.cpp": "d1a2ce42e649305416665091ecee4523c1638721d42cca34b51a03bbcfce3288",
}
RATES = (4_500_000_000, 8_000_000_000)


def canonical(data):
    return (json.dumps(data, sort_keys=True, allow_nan=False, indent=2) + "\n").encode()


def markers(rows, host):
    begins, ends, ranks, tiles = {}, {}, defaultdict(list), {}
    for r in rows:
        if r.call > 2:
            continue
        cell = (r.call, r.tile, r.layer)
        if r.kind == 3:
            tiles[cell[:2]] = r.ns
        elif r.kind == 9:
            begins.setdefault(cell, r.ns)
        elif r.kind == 23:
            ends[cell] = r.ns
        elif r.kind == 27:
            check(r.wave in (-1, 0) and r.b == len(ranks[cell]), "row/wave authority")
            ranks[cell].append(r.ns)
    check(set(begins) == set(ends), "cell endpoints")
    for cell, times in ranks.items():
        check(begins[cell] <= times[0] <= times[-1] <= ends[cell], "rank markers")
        c, t, layer = cell
        if layer:
            check(ends[c, t, layer - 1] <= begins[cell], "inter-layer order")
    spans = [(a, b) for c, a, b in host["callback_spans"] if c <= 2]
    check(all(b <= a for (_, b), (a, _) in zip(spans, spans[1:], strict=False)), "overlap")
    return begins, ends, ranks, tiles, spans


def contracted(spans):
    starts, ends = zip(*spans, strict=True)
    prefix = [0, *accumulate(b - a for a, b in spans)]

    def clock(t):
        i = bisect_right(ends, t)
        partial = max(0, t - starts[i]) if i < len(starts) else 0
        return t - prefix[i] - partial

    return clock


def windows(site, markers_, horizon, release):
    """Earliest source first; no forecast across a call or tile."""
    begins, ends, ranks, tiles, _ = markers_
    c, t, layer, wave = site
    check(wave in (0, -1), "non-first demand")
    deadline = begins[c, t, layer]
    result = []
    for src in range(max(0, layer - horizon), layer):
        cell = c, t, src
        if cell not in ranks or not ranks[cell]:
            raise ValueError("INCONCLUSIVE source rows unavailable")
        left = tiles[c, t] if src == 0 else ends[c, t, src - 1]
        right = ranks[cell][-1]
        check(left <= begins[cell] <= right <= deadline, "invalid source bracket")
        result.append((left if release == "earliest_outer" else right, deadline))
    return result


def batches(seen, n, width):
    for i, (r, d) in enumerate(seen):
        if not n or (width == "four_per_target" and i):
            break
        quantity = n if width == "unlimited" else min(n, 4)
        yield r, d, quantity
        n -= quantity


def early_capacity(groups, rate, scale=NS):
    """EDF maximizes delivered work with preemption, common rates and per-job deadlines."""
    arrivals = defaultdict(list)
    times = set()
    for release, deadline, size in groups:
        check(0 <= release <= deadline and size >= 0, "invalid EDF window")
        if release < deadline and size:
            times.update((release, deadline))
            arrivals[release].append((deadline, size * scale))
    events = sorted(times)
    done = 0
    active = []
    for t, stop in zip(events, events[1:], strict=False):
        while active and active[0][0] <= t:
            heapq.heappop(active)
        for item in arrivals[t]:
            heapq.heappush(active, item)
        capacity = (stop - t) * rate
        while active and capacity:
            deadline, left = heapq.heappop(active)
            amount = min(left, capacity)
            done += amount
            capacity -= amount
            if amount < left:
                heapq.heappush(active, (deadline, left - amount))
    return done


def compute_budget(first, decode, callback_ns, residual_ns):
    base = first - callback_ns + residual_ns
    out = {"first_at_observed_decode_ns": base, "observed_margin_ns": 10 * NS - base}
    for rate in (6, 8, 10):
        # A fractional-nanosecond saving is rounded up in the candidate's favour.
        saved = max(0, decode - (47 * NS // rate))
        out[f"margin_at_{rate}_ns"] = 10 * NS - base + saved
    target = decode + 10 * NS - base
    out["max_decode_duration_ns_if_saved_before_first"] = (
        min(decode, target) if target > 0 else None
    )
    if base <= 10 * NS:
        out["min_decode_rate_for_both_outputs_per_s"] = 6.0
    elif target > 0:
        out["min_decode_rate_for_both_outputs_per_s"] = max(6, 47 * NS / target)
    else:
        out["min_decode_rate_for_both_outputs_per_s"] = None
    return out


def arithmetic(mark, tiers):
    ranks = mark[2]
    out = {}
    for h in (1, 2):
        cells = {cell: len(v) for cell, v in ranks.items() if cell[2] >= h}
        check(
            all(
                (c, t, layer - h) in ranks and len(ranks[c, t, layer - h]) >= n
                for (c, t, layer), n in cells.items()
            ),
            "projected position absent at source",
        )
        n = sum(cells.values())
        crossing = sum(v for (_, _, layer), v in cells.items() if tiers[layer] != tiers[layer - h])
        dests = len({layer for _, _, layer in cells})
        out[str(h)] = {
            "eligible_row_destination_pairs": n,
            "dense_gate_mac": n * 2880 * 128,
            "destination_matrices": dests,
            "distinct_matrix_bytes_per_horizon": dests * 2880 * 128 * 4,
            "cross_tier_position_pairs": crossing,
            "cross_input_f32_bytes_if_copied": crossing * 2880 * 4,
            "layer35_rows": sum(v for (_, _, layer), v in cells.items() if layer == 35),
            "by_call_tile": {
                f"{c}.{t}": sum(v for (a, b, _), v in cells.items() if (a, b) == (c, t))
                for c, t in sorted(mark[3])
            },
        }
    return out


def assess(tag, rows, receipt, root, banks, tiers, prior):
    host = COST["NATIVE"]["host_trace"](rows)
    route, strict, cpu = Q["read_current"](rows, tiers)
    check(
        route == prior["route"] and (len(strict), len(cpu)) == (567, 375),
        "route and strict denominator",
    )
    check(
        COST["CLIENT"]["inspect"](root / "ON", receipt, host["calls"])["sample_call"] == 46,
        "first final",
    )
    t2 = json.loads((root / "ON/raw/T2-result.json").read_bytes())
    decode = int(Decimal(str(t2["timings"]["predicted_ms"])) * 10**6)
    first = int(Decimal(str(t2["stream_metrics"]["first_final_content_chunk_s"])) * NS)
    row = receipt["rows"][1]
    check(
        row["functional"] == "PASS"
        and row["cache_n"] == 2044
        and row["prompt_n"] == 153
        and row["predicted_n"] == row["completion_n"] == 47
        and row["completion"] == "stop"
        and abs(row["first_final_s"] * NS - first) < 2
        and abs(row["decode_s"] * NS - decode) < 2,
        "actual clocks",
    )
    mark = markers(rows, host)
    shrink = contracted(mark[-1])
    total_cb = sum(b - a for a, b in mark[-1])
    result = {
        "first_final_ns": first,
        "decode_ns": decode,
        "all_prefill_callback_ns": total_cb,
        "route": route,
        "projection": arithmetic(mark, tiers),
        "banks": {},
    }
    ranks = Q["L"]["ranks"](rows, 1)
    signature = (Q["bindings"](rows), ranks, strict, tiers)
    for name, bank in banks.items():
        remaining = Counter(site for key, site in strict.items() if key not in bank)
        by_tier = dict(Counter(tiers[k[0]] for k in strict.keys() & bank))
        if name != "none":
            info = prior["banks"][name]
            check(by_tier == info["strict_prefill_t2_hits"], "bank hit identity")
            deliveries, _ = Q["delivery"](rows, bank, tiers)
            check(deliveries == info["t2_read_only_bank_same_reservations"], "bank deliveries")
        tests = []
        total = sum(remaining.values()) * SIZE
        for h in (1, 2):
            for release in ("ranks_observed", "earliest_outer"):
                for width in ("unlimited", "four_per_target", "four_per_horizon"):
                    tasks = []
                    for site, count in remaining.items():
                        spans = windows(site, mark, h, release)
                        tasks.extend((r, d, n * SIZE) for r, d, n in batches(spans, count, width))
                    admitted = sum(v for _, _, v in tasks)
                    check(admitted <= total, "double counted jobs")
                    jobs = total // SIZE
                    limits = []
                    for rate in RATES:
                        wall = early_capacity(tasks, rate)
                        compact = early_capacity(
                            [(shrink(r), shrink(d), v) for r, d, v in tasks], rate
                        )
                        check(0 <= compact <= wall <= NS * admitted, "inconsistent overlap bounds")
                        missing = total * NS - compact
                        residual = missing // rate
                        limits.append(
                            {
                                "bytes_per_s": rate,
                                "wall_early_bytes_floor": wall // NS,
                                "contracted_early_bytes_floor": compact // NS,
                                "contracted_late_bytes_ceil": (missing + NS - 1) // NS,
                                "residual_extra_wall_floor_ns": residual,
                                "costs": compute_budget(first, decode, total_cb, residual),
                            }
                        )
                    tests.append(
                        {
                            "horizon": h,
                            "release": release,
                            "width": width,
                            "source_jobs": jobs,
                            "licensed_jobs": admitted // SIZE,
                            "limits": limits,
                        }
                    )
        result["banks"][name] = {
            "strict_bank_hits": by_tier,
            "uncovered_layer0_jobs": sum(n for s, n in remaining.items() if s[2] == 0),
            "windows": tests,
        }
    return result, signature


def run(archive, backend):
    check(
        digest(HERE / "protocol.md") == METHOD and digest(HERE / "projection.md") == ARITHMETIC,
        "method",
    )
    for name, sha in SOURCES.items():
        check(digest(backend / name) == sha, "graph source " + name)
    check(
        digest(NAT.parent / "observer.patch")
        == "44d8dbccb38711a645b0398b4cc73c8cdc19f6c29a77fa31f0f08f111c49700c",
        "PFJ emit site",
    )
    prior = pinned(NAT / "prefill_retention/result.json", PRIORS)
    roots = {k: archive / ("part-" + k[1:]) / v[0] for k, v in COST["SOURCES"].items()}
    for tag, root in roots.items():
        manifest = pinned(root.parent / "manifest.json", COST["SOURCES"][tag][2])
        COST["authenticate_raw"](root, manifest, ["raw/T2-result.json", "raw/T2-request.jsonl"])
    root = roots["P106"]
    seal, rows, tiers, source = Q["read_new"](root, COST["SOURCES"]["P106"][1])
    fam = pinned(root / "family.json", COST["SOURCES"]["P106"][1])
    arm = pinned(root / "ON/arm.json", fam["arms"]["ON"]["sha256"])
    rec = pinned(root / "ON/receipt.json", arm["receipt_sha256"])
    check(source == prior["new_source"], "causal T1")
    banks = {
        "none": set(),
        **{k: set(map(tuple, v["ordered_keys"])) for k, v in seal["banks"].items()},
    }
    check(
        set(banks) == {"none", "lru", "prefill"}
        and len(banks["lru"]) == len(banks["prefill"]) == 353,
        "banks",
    )
    p106, a = assess("P106", rows, rec, root, banks, tiers, prior)
    del rows
    root = roots["P97"]
    _, _, rec, audit = COST["CHAIN"]["chain"](root, Q["P97"])
    rows, header = T["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
    check(header == audit["header"], "P97 journal")
    log = root / "ON/raw" / rec["native_ids"]["raw_stderr_file"]
    check(
        digest(log) == rec["native_ids"]["stderr_sha256"]
        and T["mapping"](log.read_bytes(), rows)[0] == tiers,
        "P97 placement",
    )
    p97, b = assess("P97", rows, rec, root, banks, tiers, prior)
    check(
        a == b, "different entry, ordered routes, strict demand sites or placement between P97/P106"
    )
    for info in (p97, p106):
        check(info["projection"] == p97["projection"], "eligible rows")
    return {
        "status": "REPRODUCED_CONDITIONAL_POST_ATTENTION_WINDOWS",
        "protocol_sha256": METHOD,
        "projection_protocol_sha256": ARITHMETIC,
        "code_sha256": digest(Path(__file__)),
        "source_sha256": SOURCES,
        "prior_sha256": PRIORS,
        "P97_journal_sha256": header["journal_sha256"],
        "T1": source,
        "tier_population": prior["strict_prefill_t2_jobs"],
        "bank_work": {
            k: {
                field: v[field]
                for field in (
                    "copies",
                    "t1_acquisition_bytes",
                    "strict_prefill_t2_delivery_bytes",
                    "t2_read_only_bank_same_reservations",
                )
            }
            for k, v in prior["banks"].items()
        },
        "P97": p97,
        "P106": p106,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "backend", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        report = run(a.archive, a.backend)
    except Exception as e:
        status = (
            "INCONCLUSIVE_SOURCE_WINDOW" if str(e).startswith("INCONCLUSIVE") else "FAIL_PRESERVED"
        )
        report = {"status": status, "reason": str(e), "error": type(e).__name__}
    (a.new_output_dir / "receipt.json").write_bytes(canonical(report))
    print(report["status"])
    raise SystemExit(int(report["status"] != "REPRODUCED_CONDITIONAL_POST_ATTENTION_WINDOWS"))
