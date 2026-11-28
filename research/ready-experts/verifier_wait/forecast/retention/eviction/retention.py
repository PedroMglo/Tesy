"""Replay finite retention at the last primary or secondary eviction of a routed expert."""

import argparse
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
P = run_path(HERE / "release.py")
F, S, E, need, verified, sha, save = (
    P[k] for k in ("F", "S", "E", "need", "verified", "sha", "save")
)
R, T = E["R"], E["T"]
PROTO = P["PROTO"]
TRAIN = "e85d2a4a3a42b461e99535a0055be0b2e0e9a1231864859bc735bed93b355909"


def feature_tiles(model, ids):
    # The policy receives only the current admitted prompt return. Layer 35 uses a
    # fixed last-position proxy, including on a tile for which no output is requested.
    tiles = []
    for start in range(0, len(ids), 32):
        tokens = ids[start : start + 32]
        scores = []
        for layer in range(36):
            total = Counter()
            for token in tokens[-1:] if layer == 35 else tokens:
                count, n = model.token_scores(token, layer)
                for expert, observed in count.items():
                    total[expert] += observed * 1_000_000 // n
            scores.append([total[e] for e in range(128)])
        tiles.append(scores)
    return tiles


def extract(a):
    table = F["Frequencies"].unpack(verified(a.model, TRAIN))
    work = verified(a.work, F["WORK"])
    start = work["cached"]
    tiles = []
    for end in work["t2_ends"]:
        tiles.append(feature_tiles(table, work["t2"][start:end]))
        start = end
    need(
        start == len(work["t2"])
        and [len(t) for t in tiles] == [1, 5]
        and work["cached"] == 2044
        and work["t2_ends"] == [2049, 2197],
        "5+148 submitted IDs",
    )
    return dict(protocol=PROTO, training=TRAIN, work=F["WORK"], tile_scores=tiles)


@dataclass(frozen=True)
class Event:
    index: int
    site: tuple
    key: tuple
    slot: int
    generation: int
    cold: bool
    lost: tuple | None
    source: str | None
    origin_slot: int | None


def events(tx):
    freq = Counter({(layer, e): n for layer, e, n in tx["counts"]})
    caps = T["quotas"](freq)
    primary = {(layer, s): (e, g) for layer, s, e, g in tx["initial"]}
    present = {(layer, e) for (layer, _), (e, _) in primary.items()}
    seed = list(map(tuple, tx["seed"]))
    pools = [
        T["Pool"](cap, [k for k in seed if k not in present and T["stage"](k[0]) == i], freq)
        for i, cap in enumerate(caps)
    ]
    effects, reference = T["run_order"](tx["reservations"], tx["initial"], seed, freq, caps, True)
    out = []
    for i, (row, effect) in enumerate(zip(tx["reservations"], effects, strict=True)):
        c, t, layer, s, g, e, old = row
        if c > 2:
            break
        group, key, victim = T["stage"](layer), (layer, e), (layer, old)
        pool = pools[group]
        before = pool.held.copy()
        need(
            primary[layer, s] == (old, g - 1) and key not in present and victim in present,
            "primary generation",
        )
        src, dst = pool.reserve(key, victim)
        need([group, src, dst] == effect, "secondary movement")
        # All other primary owners are invariant during this transaction.
        removed = (before.keys() | {victim}) - (pool.held.keys() | {key})
        need(len(removed) <= 1, "more than one last-owner loss")
        lost = next(iter(removed), None)
        source = origin_slot = None
        if lost == victim:
            source, origin_slot = ("primary_GPU" if group else "primary_CPU"), s
        elif lost is not None:
            source, origin_slot = "bank_RAM", before[lost]
            need(origin_slot == dst and lost != key, "wrong secondary overwrite")
        primary[layer, s] = e, g
        present.remove(victim)
        present.add(key)
        out.append(Event(i, (c, t, layer), key, s, g, src is None, lost, source, origin_slot))
    independent = F["Inventory"](tx)
    need(
        primary == independent.primary
        and all(a.held == b.held for a, b in zip(pools, independent.pools, strict=True))
        and reference == independent.bank
        and len(out) == 1263
        and sum(v.cold for v in out) == 892,
        "decode entry or population",
    )
    return out


def demand_intervals(rows):
    previous = {}
    intervals = {}
    last_call = None
    for site, group in groupby(rows, key=lambda r: r.site):
        group = list(group)
        if site[0] != last_call:
            previous.clear()
            last_call = site[0]
        # Loss occurs at reservation, after the incoming demand. The auxiliary
        # reference stays pinned past all reservations of the consuming site.
        end = 2 * group[-1].index + 2
        for row in group:
            if row.cold and row.key in previous:
                loss = previous.pop(row.key)
                iv = R["Interval"](2 * loss.index + 1, end, *row.key)
                need(iv not in intervals, "duplicate demand interval")
                intervals[iv] = loss, row
            if row.lost is not None:
                need(row.lost not in previous, "lost again without a new acquisition")
                previous[row.lost] = row
    return intervals


def score(grid, site, key):
    c, t, current = site
    layer, e = key
    # Primary and secondary eviction orders within each stage are independent
    # of how the two stages interleave. The next site of this layer is known.
    first = t - 1 + int(layer <= current)
    return sum(tile[layer][e] for tile in grid[c - 1][first:])


def causal(rows, grid, mode):
    held = [{}, {}]
    captured = Counter()
    hits = {}
    prev = None
    for site, group in groupby(rows, key=lambda r: r.site):
        if site[0] != prev:
            held = [{}, {}]
            prev = site[0]
        group = list(group)
        stage = T["stage"](site[2])
        pool = held[stage]
        pins = set()
        for row in group:
            if row.key in pool:
                need(row.cold and row.key not in pins, "auxiliary/primary alias")
                iv = R["Interval"](2 * pool[row.key].index + 1, 2 * group[-1].index + 2, *row.key)
                hits[iv] = pool[row.key], row
                pins.add(row.key)
            key = row.lost
            if key is None or key in pool:
                continue
            if mode == "lexical" and not score(grid, site, key):
                continue
            if len(pool) == 2:
                choices = pool.keys() - pins
                if not choices:
                    continue
                if mode == "lexical":
                    victim = min(choices, key=lambda k: (score(grid, site, k), -pool[k].index))
                    if score(grid, site, key) <= score(grid, site, victim):
                        continue
                else:
                    victim = min(choices, key=lambda k: pool[k].index)
                del pool[victim]
            pool[key] = row
            captured[row.source] += 1
        for key in pins:
            del pool[key]
        need(len(pool) <= 2, "auxiliary capacity")
    return hits, captured


def prices(tables, base, cfg, prior, service):
    out = defaultdict(list)
    order = cfg["plan"]["order"]
    for tag, raw in service["journals"].items():
        relaxed = R["grant_original_pairs"](raw, base, order)
        for mode, served in tables.items():
            for variant, journal in (("actual_pairs", raw), ("free_original_pairs", relaxed)):
                price = T["priced"](tag, served, journal, order, cfg["layout"], cfg["pipeline"])[
                    "copied"
                ]
                ns = price["limits_by_Bps"][R["RATE"]]["prefill_ns"]
                cold = price["counts"]["prefill"]["cold"]
                for original in prior["arms"]["off"]:
                    if original["tag"] != tag:
                        continue
                    first = [n + ns - original["prefill_ns"] for n in original["first_ns"]]
                    out[mode].append(
                        dict(
                            pairs=variant,
                            tag=tag,
                            W=original["W"],
                            repeat=original["repeat"],
                            prefill_ns=ns,
                            cold=cold,
                            first_ns=first,
                            decode_ns=original["decode_ns"],
                            common_slack_ns=min(
                                10**10 - first[1], P["M"]["P"]["DECODE_MAX"] - original["decode_ns"]
                            ),
                        )
                    )
                    if mode == "off":
                        need(first == original["first_ns"] and cold == 892, "disabled price")
    return out


def run(data):
    grid = data["tile_scores"]
    need(
        (data["protocol"], data["training"], data["work"]) == (PROTO, TRAIN, F["WORK"])
        and [len(t) for t in grid] == [1, 5]
        and all(
            len(tile) == 36
            and all(
                len(layer) == 128 and all(isinstance(n, int) and n >= 0 for n in layer)
                for layer in tile
            )
            for call in grid
            for tile in call
        ),
        "private feature boundary",
    )
    parent = verified(HERE.parent / "evidence-entry-20261128-r01/receipt.json", P["P"]["ENTRY"])
    prior = verified(HERE.parent / "evidence-20261128-r01/receipt.json", parent["prior"])
    tx = verified(S["PATHS"]["transactions"], prior["sources"]["transactions"])
    service = verified(S["PATHS"]["service"], prior["sources"]["service"])
    cfg = {k: verified(T["E"] / (k + ".json"), h) for k, h in prior["geometry"].items()}
    base, _, all_hits, _ = E["inventory"](tx)
    rows = events(tx)
    possible = demand_intervals(rows)
    actual = {(r.site, r.key[1]) for _, r in possible.values()}
    reference = {
        (site, e)
        for site, hits in all_hits.items()
        if site[0] <= 2
        for e in hits - base.get(site, set())
    }
    need(len(actual) == len(possible) == 166 and actual == reference, "same 166 evictions")
    stage_sets = [{iv for iv in possible if T["stage"](iv.layer) == i} for i in (0, 1)]
    curve = {}
    selected = {}
    for cap in (0, 1, 2, 4, 8, 16, 32, 64):
        sets = [R["maximum"](s, cap) for s in stage_sets]
        need(all(R["pressure"](s) <= cap for s in sets), "offline capacity witness")
        curve[str(cap)] = [len(s) for s in sets]
        if cap == 2:
            selected["count_oracle"] = set.union(*sets)
    selected.update(off=set(), unlimited=set(possible))
    captures = {}
    for name in ("recency", "lexical"):
        hits, counts = causal(rows, grid, name)
        need(
            all(possible.get(k) == v for k, v in hits.items())
            and len(hits) <= len(selected["count_oracle"]),
            "causal witness outside the envelope",
        )
        selected[name] = set(hits)
        captures[name] = dict(counts)
    tables = {}
    witness = {}
    for name, subset in selected.items():
        served = {s: v.copy() for s, v in base.items()}
        intervals = []
        for iv in sorted(subset):
            a, b = possible[iv]
            served.setdefault(b.site, set()).add(b.key[1])
            intervals.append(
                [
                    a.index,
                    b.index,
                    *a.site,
                    a.source,
                    a.origin_slot,
                    *b.site,
                    b.key[1],
                    b.slot,
                    b.generation,
                ]
            )
        tables[name] = served
        witness[name] = intervals
    arms = prices(tables, base, cfg, prior, service)
    for name, vs in arms.items():
        need(
            len(vs) == 16 and all(a["cold"] == 892 - len(selected[name]) for a in vs),
            "arm conservation",
        )
    for a in arms["unlimited"]:
        if a["pairs"] == "free_original_pairs":
            base_arm = next(
                v
                for v in parent["arms"]
                if (v["tag"], v["W"], v["repeat"]) == (a["tag"], a["W"], a["repeat"])
            )
            need(a["first_ns"] == base_arm["first_ns"], "unlimited price")
    optimistic = [a for a in arms["lexical"] if a["pairs"] == "free_original_pairs"]
    return dict(
        protocol=PROTO,
        evidence="TRACE_DERIVED_FINITE_PRIMARY_AND_BANK_LOSS",
        status=P["M"]["P"]["decision"](optimistic),
        program=sha(Path(__file__)),
        fixed_caps=[2, 2],
        allocated_aligned_B=4 * P["SIZE"],
        peak_all=[R["pressure"](s) for s in stage_sets],
        opportunities=[len(s) for s in stage_sets],
        curve=curve,
        hits={k: len(v) for k, v in selected.items()},
        captures=captures,
        capture_payload_B={k: sum(c.values()) * T["PAYLOAD"] for k, c in captures.items()},
        lost_by_tier=dict(Counter(r.source for r in rows if r.lost)),
        sources=prior["sources"],
        prices=arms,
        witness=witness,
        full_model_requests=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("--model", required=True, type=Path)
    cap.add_argument("--work", required=True, type=Path)
    cap.add_argument("--new-output-dir", required=True, type=Path)
    grade = sub.add_parser("grade")
    grade.add_argument("--scores", required=True, type=Path)
    dest = grade.add_mutually_exclusive_group(required=True)
    dest.add_argument("--check", type=Path)
    dest.add_argument("--new-output-dir", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        need(sha(HERE / "protocol.md") == PROTO, "frozen protocol")
        if a.action == "capture":
            save(a.new_output_dir / "scores.json.gz", extract(a))
            print("PASS", sha(a.new_output_dir / "scores.json.gz"))
        else:
            result = run(F["load"](a.scores)) | dict(scores_sha256=sha(a.scores))
            if a.check:
                need(result == F["load"](a.check), "changed finite retention witness")
            else:
                save(a.new_output_dir / "receipt.json", result)
            print(result["status"], result["hits"], result["peak_all"])
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise


if __name__ == "__main__":
    main()
