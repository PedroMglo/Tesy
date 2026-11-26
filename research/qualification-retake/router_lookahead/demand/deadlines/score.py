"""Conditional C292 deadlines for whole, fixed-price reads on one idle link."""

import argparse
import json
import os
from collections import Counter, defaultdict, deque
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent
M = run_path(str(HERE.parent / "score.py"))
P, TF, need = M["P"], M["TF"], M["need"]
METHOD = "7b54d6327c270c027c8c6ce0609aa9aa4af0d4adc1553c1317bfc0d1e31f676a"
PARENT = "6a842b9c9036d0c659db9262df5175f2e43793a29de0cd25bd894bb1f66eea9b"
RECEIPT = "5e83418c00905348b46a442f0caee4affbf7ab3073a3faaeff8f958971e02c05"
WINDOW = M["AUDIT"]["WINDOW"]
NANO = 10**9
PRICES = (4_500_000_000, 8_000_000_000)
CUTS = ("reserve", "accept_or_barrier", "barrier")


def job_deadlines(events):
    """Accepts refer to job of reservation, while E19 refers to wave of first use."""
    fifo, jobs, wave, uses = deque(), {}, defaultdict(dict), {}
    for i, r in enumerate(events):
        key = M["AUDIT"]["identity"](r)
        site = (r.call, r.tile, r.layer, r.wave)
        if r.kind in (9, 19, 20, 23):
            need(r.kind not in wave[site], "repeated wave marker")
            wave[site][r.kind] = (i, r.ns)
        elif r.kind == 11:
            need(key not in jobs, "generation reserved twice")
            jobs[key] = {11: (i, r.ns)}
        elif r.kind == 12:
            need(key in jobs, "unreserved enqueue")
            fifo.append((key, i, r.ns))
        elif r.kind in (13, 14, 28):
            need(fifo and fifo[0][0] == key, "FIFO identity")
            _, enqueue, stamp = fifo.popleft()
            if r.kind == 13:
                need(
                    13 not in jobs[key] and jobs[key][11][0] < enqueue < i and stamp <= r.ns,
                    "claim",
                )
                jobs[key][13] = (i, r.ns)
        elif r.kind in (30, 17):
            need(r.kind not in jobs[key], "duplicate read/publication")
            jobs[key][r.kind] = (i, r.ns)
        elif r.kind == 10:
            need(9 in wave[site] and 19 not in wave[site], "demand outside wave")
            uses.setdefault(key, (site, (i, r.ns)))
    need(not fifo, "undrained FIFO")
    for v in wave.values():
        need(
            set(v) == {9, 19, 20, 23} and [v[k] for k in (9, 19, 20, 23)] == sorted(v.values()),
            "incomplete wave",
        )
        need(v[9][1] <= v[19][1] <= v[20][1] <= v[23][1], "host clock")
    result = {}
    for key, job in jobs.items():
        need(set(job) == {11, 13, 30, 17}, "generation without complete transport")
        order = [job[k] for k in (11, 13, 30, 17)]
        need(
            all(i < j and a <= b for (i, a), (j, b) in zip(order, order[1:], strict=False)),
            "generation clocks",
        )
        if key not in uses:
            continue
        site, (demand_idx, demand_ns) = uses[key]
        (reserve_idx, reserve), (_, accept), _, (publication_idx, publication) = order
        need(
            reserve_idx < demand_idx < wave[site][19][0]
            and reserve <= demand_ns <= wave[site][19][1],
            "first authoritative demand",
        )
        need(
            publication_idx < wave[site][20][0] and publication <= wave[site][20][1],
            "consumer resumed before publish",
        )
        result[key] = (site, (reserve, min(accept, wave[site][19][1]), wave[site][19][1]))
    return result


def collect(args):
    P.file(HERE / "protocol.md", METHOD)
    P.file(HERE.parent / "score.py", PARENT)
    parent = json.loads(P.file(args.original / "receipt.json", RECEIPT))
    audit = {"status": "FAIL_PRESERVED", "method_sha256": M["METHOD"], "program_sha256": PARENT}
    M["run"](args, audit)
    need(audit == parent, "reproduce parent calibration, ordered ranks and all keys")
    path = args.part95 / "tesy-c292-pack-numeric-physical-20261125-r02/overlay_on/raw/phase.pfj1"
    events, header = M["AUDIT"]["read_journal"](path)
    need(header == parent["journal"], "journal identity")
    tiles, _, _, releases, _, demands, reserves = M["journal"](events)
    deadlines = job_deadlines(events)
    index = {p[0]: tile for tile, p in tiles.items()}
    source, _, _ = P.capture(args.part23)
    calibrated = json.loads(P.file(HERE.parents[1] / "tf32/receipt.json", M["CAL"]))
    params = TF["parameters"](args.c7, args.bundle, calibrated["weights_sha256"])
    P.project = TF["surrogate"](params)
    sites, totals = [], defaultdict(Counter)
    cross_wave = same_wave = 0
    for (phase, layer), gold in source.items():
        if layer == 0:
            continue
        tile = index[P.PHASES[phase][0]]
        site = (*tile, layer)
        ix, release, occupied = releases[site]
        src = source[phase, layer - 1]
        pos = gold["start"] - src["start"]
        n = len(gold["ffn_moe_topk"])
        need(0 <= pos < pos + n <= len(src["attn_post_norm"]), "source output mask")
        pred = P.infer(src["attn_post_norm"][pos : pos + n], params[layer - 1][0], params[layer])
        offered, _ = M["choose"](pred, occupied, 4)
        requested = set(demands[site])
        generations = {}
        for j, key, origin_wave, _ in reserves[site]:
            if key[-1] not in occupied and key in requested and key[-1] not in generations:
                need(ix < j, "decision after reservation")
                generations[key[-1]] = (key, origin_wave)
        hits = {}
        for expert in offered:
            if expert in generations:
                key, origin_wave = generations[expert]
                use, ds = deadlines[key]
                need(use[:3] == site and min(ds) >= release, "generation, site or release")
                hits[expert] = ds
                cross_wave += int(origin_wave != use[3])
                same_wave += int(origin_wave == use[3])
        group = ("prefill" if phase.startswith("prefill") else "decode") + (
            "/CPU" if layer < 25 else "/CUDA"
        )
        totals[group].update(sites=1, offers=len(offered), jobs_hit=len(hits))
        sites.append((ix, release, group, offered, hits))
    for group, c in totals.items():
        need(
            all(parent["counts"][group + "/projection/four"][k] == v for k, v in c.items()),
            "parent offers/sites/hits",
        )
    return (
        sorted(sites),
        dict(totals),
        {"same_wave": same_wave, "earlier_reservation_wave": cross_wave},
    )


def max_completions(gaps, rate, window=WINDOW):
    """EDF with rejection is exact for equal-size jobs available at the same instant."""
    complete = 0
    price = window * NANO
    for gap in sorted(gaps):
        if (complete + 1) * price <= gap * rate:
            complete += 1
    return complete


def summarize(values):
    return {
        "count": len(values),
        "minimum": min(values, default=None),
        "median": median(values) if values else None,
        "maximum": max(values, default=None),
    }


def evaluate(sites, rate, window=WINDOW):
    price = window * NANO
    # Times in ns * bytes/s. The device cursor is never reset between measured sites.
    current = 0
    groups = defaultdict(Counter)
    budgets = defaultdict(list)
    overlap = Counter()
    previous_deadline = {cut: 0 for cut in CUTS}
    for _, release, group, offered, hits in sites:
        q = groups[group]
        q.update(sites=1, offers=len(offered), hits=len(hits), sites_with_hit=int(bool(hits)))
        done = {}
        current = max(current, release * rate)
        for expert in offered:
            current += price
            done[expert] = current
        for j, cut in enumerate(CUTS):
            gaps = [ds[j] - release for ds in hits.values()]
            need(all(g >= 0 for g in gaps), "negative price window")
            # Only sites actually wanting a hit use the oracle device.
            if gaps:
                overlap[cut] += int(release < previous_deadline[cut])
                previous_deadline[cut] = max(previous_deadline[cut], release + max(gaps))
            oracle = max_completions(gaps, rate, window)
            fifo_good = sum(done[e] <= ds[j] * rate for e, ds in hits.items())
            need(fifo_good <= oracle <= len(hits), "capacity direction")
            q.update(
                {
                    cut + "_oracle": oracle,
                    cut + "_fifo": fifo_good,
                    cut + "_oracle_sites": int(oracle > 0),
                }
            )
            if gaps:
                for cls, gap in (("earliest_due", min(gaps)), ("any_hit", max(gaps))):
                    # Signed slack for integral-nanosecond projection overhead.
                    slack = (gap * rate - price) // rate
                    budgets[group, cut, cls].append(slack)
                    q[cut + "_" + cls + "_feasible_sites"] += int(slack >= 0)
    total = Counter()
    for counts in groups.values():
        total.update(counts)
    return {
        "rate_bytes_per_s": rate,
        "read_completion_ceil_ns": (price + rate - 1) // rate,
        "sites_overlapping_previous_deadlines": {k: overlap[k] for k in CUTS},
        "by_target": dict(groups),
        "global": dict(total),
        "projector_slack_ns": {"/".join(k): summarize(v) for k, v in budgets.items()},
    }


def run(args):
    sites, totals, uses = collect(args)
    result = {str(rate): evaluate(sites, rate) for rate in PRICES}
    return {
        "status": "MEASURED_C292_CONDITIONAL_DEADLINES",
        "parent_receipt_sha256": RECEIPT,
        "journal_sha256": M["JOURNAL"],
        "calibration_sha256": M["CAL"],
        "read_window_bytes": WINDOW,
        "selected": totals,
        "first_demand": uses,
        "rates": result,
        "physical_prefetches": 0,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("part23", "part95", "c7", "bundle", "original", "new-output-dir"):
        ap.add_argument("--" + name, type=Path, required=True)
    args = ap.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    result = {
        "status": "FAIL_PRESERVED",
        "method_sha256": METHOD,
        "program_sha256": P.sha(Path(__file__).read_bytes()),
    }
    try:
        result.update(run(args))
    except Exception as exc:
        result["reason"] = f"{type(exc).__name__}: {exc}"
    body = json.dumps(result, sort_keys=True, indent=2) + "\n"
    need(len(body) < 2 << 20, "output size")
    with (args.new_output_dir / "receipt.json").open("x") as out:
        out.write(body)
    print(result["status"], result.get("reason", ""))
    raise SystemExit(int(result["status"] == "FAIL_PRESERVED"))
