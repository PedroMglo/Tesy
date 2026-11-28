"""Price auxiliary copies of weights already supplied in one external prefill call."""

import argparse
import os
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
F = run_path(HERE.parent / "forecast.py")
T, need, save, sha, verified = (F[k] for k in ("T", "need", "save", "sha", "verified"))
S = F["SERVICE"]
PROTOCOL = "b3809edab82d325c20b20c1d90e169aa9f1b2c74b1284a30584f975501aef4bc"
LEX = "6da36ea66ea41e8fce694780b854653fadda0d5fdce536e9f20b9880c29c22d5"
CONFIG = {
    "layout": "171e1bc51f55c7fe371e758eb0adbee77efb5a8ad76b95e1d29de600c108555d",
    "pipeline": "5fc56d654b3c04e9f02acb7c5a05ab39d29ea5c2477bc962c23901b0f00230c5",
    "plan": "2ed4d1e8c2db6a0f62c4e6126923a5742e38b23f808bd417511021d0ca90a420",
}
RATE = "4500000000"


@dataclass(frozen=True, order=True)
class Interval:
    start: int
    end: int
    layer: int
    expert: int


def maximum(intervals, capacity):
    """Keep the earliest-ending intervals when occupancy exceeds the available slots."""
    chosen = set(intervals)
    live = set()
    for iv in sorted(intervals):
        live = {old for old in live if old.end > iv.start}
        live.add(iv)
        if len(live) > capacity:
            remove = max(live, key=lambda old: (old.end, old))
            live.remove(remove)
            chosen.remove(remove)
    return chosen


def pressure(intervals):
    changes = Counter()
    for iv in intervals:
        changes[iv.start] += 1
        changes[iv.end] -= 1
    active = peak = 0
    for at in sorted(changes):
        active += changes[at]
        peak = max(peak, active)
    need(active == 0, "parking drain")
    return peak


def opportunities(sites):
    ordered = sorted(site for site in sites if site[0] <= 2)
    previous = {}
    held = [OrderedDict(), OrderedDict()]
    current_call = None
    candidates, causal = set(), set()
    captures = [0, 0]
    for idx, site in enumerate(ordered):
        call, _, layer = site
        stage = T["stage"](layer)
        if call != current_call:
            previous.clear()
            for pool in held:
                pool.clear()
            current_call = call
        pool = held[stage]
        jobs = sites[site]
        need(len({e for e, _ in jobs}) == len(jobs), "duplicate reservation in one group")
        # All consumers can read the site's entry state before its captures begin.
        for e, bank_hit in jobs:
            key = layer, e
            if not bank_hit and key in previous:
                iv = Interval(previous[key], idx, layer, e)
                candidates.add(iv)
                if key in pool:
                    causal.add(iv)
        for e, _ in jobs:
            key = layer, e
            previous[key] = idx
            if key in pool:
                pool.move_to_end(key)
            else:
                if len(pool) == 2:
                    pool.popitem(last=False)
                pool[key] = None
                captures[stage] += 1
    finite = set()
    for stage in (0, 1):
        eligible = {iv for iv in candidates if T["stage"](iv.layer) == stage}
        chosen = maximum(eligible, 2)
        need(pressure(chosen) <= 2 and pressure(causal & eligible) <= 2, "parking capacity")
        need(len(chosen) >= len(causal & eligible), "offline cardinality below recency")
        finite.update(chosen)
    return ordered, candidates, finite, causal, captures


def grant_original_pairs(raw, served, order):
    # A hit can break an adjacent cold pair. Grant every original pair its old READ
    # credit even after such a break, to bound every subset with a monotone price.
    groups = []
    for c, t, layer, *clocks, work in raw["groups"]:
        _, coupled, _, _ = T["K"]["sources"](work, order[layer], served.get((c, t, layer), ()))
        rows = [[e, 0 if e in coupled else rd, st] for e, rd, st in work]
        groups.append([c, t, layer, *clocks, rows])
    return dict(calls=raw["calls"], groups=groups)


def evaluate():
    need(sha(HERE / "protocol.md") == PROTOCOL, "protocol changed")
    parent = verified(F["CONTROL"], F["CONTROL_SHA"])
    p = {
        k: verified(S["PATHS"][k], parent["inputs"][k]) for k in ("transactions", "service", "bank")
    }
    cfg = {k: verified(T["E"] / (k + ".json"), h) for k, h in CONFIG.items()}
    lex = verified(HERE.parent / "evidence-20261128-r01/receipt.json", LEX)
    tx = p["transactions"]
    freq = Counter({(layer, expert): n for layer, expert, n in tx["counts"]})
    effects, bank = T["run_order"](
        tx["reservations"],
        tx["initial"],
        list(map(tuple, tx["seed"])),
        freq,
        T["quotas"](freq),
        True,
    )
    reference = p["bank"]["result"]
    need(bank == reference["partition"] and reference["caps"] == [252, 101], "frozen banks")
    sites, served = defaultdict(list), defaultdict(set)
    for (call, tile, layer, _, _, expert, _), (_, source, _) in zip(
        tx["reservations"], effects, strict=True
    ):
        site = call, tile, layer
        sites[site].append((expert, source is not None))
        if source is not None:
            served[site].add(expert)
    ordered, intervals, finite, causal, captures = opportunities(sites)
    jobs = sum(len(sites[site]) for site in ordered)
    hits = sum(len(served[site]) for site in ordered)
    need((jobs, hits, jobs - hits) == (1263, 371, 892), "prefill conservation")
    modes = dict(off=set(), recency=causal, count_oracle=finite, unlimited_envelope=intervals)
    arms = defaultdict(list)
    volumes = {}
    order = cfg["plan"]["order"]
    for m, selected in modes.items():
        promoted = {site: hits.copy() for site, hits in served.items()}
        for iv in selected:
            site = ordered[iv.end]
            cold = {e for e, hit in sites[site] if not hit}
            need(iv.layer == site[2] and iv.expert in cold, "credit outside a cold generation")
            promoted.setdefault(site, set()).add(iv.expert)
        peak = [pressure({iv for iv in selected if T["stage"](iv.layer) == s}) for s in (0, 1)]
        volumes[m] = dict(
            saved=len(selected),
            aligned_bytes=(892 - len(selected)) * S["ALIGNED"],
            live_by_stage=peak,
            witness=[[*ordered[iv.start], *ordered[iv.end], iv.expert] for iv in sorted(selected)],
        )
        for tag, raw in p["service"]["journals"].items():
            measured_sites = {
                (call, tile, layer): {row[0] for row in work}
                for call, tile, layer, *_, work in raw["groups"]
                if call <= 2 and work
            }
            need(measured_sites == {s: {e for e, _ in sites[s]} for s in ordered}, "job identity")
            if m == "unlimited_envelope":
                raw = grant_original_pairs(raw, served, order)
            price = T["priced"](tag, promoted, raw, order, cfg["layout"], cfg["pipeline"])["copied"]
            before = reference["arms"][tag]["trained"]["copied"]
            need(m != "off" or price == before, "reproduce full disabled control")
            count = price["counts"]["prefill"]
            need(count["cold"] == 892 - len(selected), "I/O census")
            base_ns = before["limits_by_Bps"][RATE]["prefill_ns"]
            after_ns = price["limits_by_Bps"][RATE]["prefill_ns"]
            for v in lex["arms"][RATE]["token"][tag]:
                ff = [n + after_ns - base_ns for n in v["first_ns"]]
                arms[m].append(
                    dict(
                        tag=tag,
                        W=v["W"],
                        repeat=v["repeat"],
                        prefill_ns=after_ns,
                        prefill_saved_ns=base_ns - after_ns,
                        first_ns=ff,
                        decode_ns=v["decode_ns"],
                        extra_budget_ns=min(10**10 - ff[1], 47 * 10**9 // 6 - v["decode_ns"]),
                    )
                )
    for tag in p["service"]["journals"]:
        best = next(a["prefill_ns"] for a in arms["unlimited_envelope"] if a["tag"] == tag)
        need(
            all(best <= a["prefill_ns"] for rows in arms.values() for a in rows if a["tag"] == tag),
            "envelope must dominate every finite schedule",
        )
    any_oracle = any(
        v["first_ns"][0] <= 10**10 and v["decode_ns"] <= 47 * 10**9 // 6
        for v in arms["unlimited_envelope"]
    )
    status = "INCONCLUSIVE" if any_oracle else "NO_GO"
    if all(v["extra_budget_ns"] >= 0 for v in arms["recency"]):
        status = "GO_FIXTURE_ONLY"
    return dict(
        status=status,
        evidence="TRACE_DERIVED_FIXED_SERVICE",
        program=sha(Path(__file__)),
        protocol=PROTOCOL,
        individual=LEX,
        sources=parent["inputs"],
        geometry=CONFIG,
        prefill_jobs=jobs,
        baseline_bank_hits=hits,
        baseline_cold=jobs - hits,
        aligned_parking_B=4 * S["ALIGNED"],
        recency_captures_by_stage=captures,
        recency_capture_payload_B=sum(captures) * T["PAYLOAD"],
        volumes=volumes,
        arms=arms,
        gpu_forwards=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--new-output-dir", type=Path)
    g.add_argument("--check", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        r = evaluate()
        if a.check:
            need(r == F["load"](a.check), "changed retention proof")
        else:
            save(a.new_output_dir / "receipt.json", r)
        print(r["status"], {k: v["saved"] for k, v in r["volumes"].items()})
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise


if __name__ == "__main__":
    main()
