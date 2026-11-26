"""Optimize compatible decode paths jointly with a fixed T1 bank and prefill credit."""

import argparse
import hashlib
import json
from collections import Counter
from fractions import Fraction
from functools import cache
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
BANK = run_path(str(HERE / "bank.py"))
ENV, HTTP, AUDIT, G, need, save = (BANK[k] for k in ("ENV", "HTTP", "AUDIT", "G", "need", "save"))
RATE, WINDOW = BANK["RATE"], BANK["WINDOW"]
Edge = ENV["Edge"]
METHOD = "f262a4ce9a7a3d236580e0926968d878e7be4b1a14d69f46383208f5986c4f75"
PRICES = "faff519fbe22d9a50455247de29866f8743b448cb0743b1309082fecc565fd2d"
MILLION = 10**6


def repriced(edges, hits, ppm, cut):
    result = []
    for e in edges:
        if e.block:
            result.append(e)
            continue
        discount = min(e.us, Fraction(hits[e.start + 3] * WINDOW * ppm, RATE))
        result.append(
            e._replace(us=e.us - discount, early_us=e.early_us - (discount if e.end <= cut else 0))
        )
    return result


def history(path):
    return tuple((e.start, e.end, e.arm, e.block) for e in path)


def register(path, paths):
    # Run-length coding of consecutive individual steps, retaining every block boundary.
    runs = []
    for s, t, arm, block in history(path):
        if not block and runs and not runs[-1][3] and runs[-1][1:3] == [s, arm]:
            runs[-1][1] = t
        else:
            runs.append([s, t, arm, block])
    h = hashlib.sha256(json.dumps(runs, separators=(",", ":")).encode()).hexdigest()
    need(paths.setdefault(h, runs) == runs, "unique witness")
    return h


def fixture():
    serial = [Edge(j, j + 1, 10, 10 if j < 2 else 0, "S", False) for j in range(3)]
    block = Edge(0, 2, 15, 15, "B", True)
    for ppm, uses_block in ((0, True), (MILLION, False)):
        edges = repriced(serial + [block], Counter({3: 1}), ppm, 2)
        full = ENV["frontier"](edges, 3, 2)
        by_hand = [edges[:3], [edges[-1], edges[2]]]
        expect = min(by_hand, key=ENV["clocks"])
        need(
            len(full) == 1
            and history(full[0]) == history(expect)
            and any(e.block for e in full[0]) == uses_block,
            "bank changes the winning path",
        )
    return True


def select(paths, first_outside, decode_outside, io_us):
    def metrics(p):
        early, total = ENV["clocks"](p)
        first = first_outside + io_us + early
        decode = decode_outside + total
        return min(10 * MILLION - first, Fraction(47 * MILLION, 6) - decode), first, decode

    choices = [(metrics(p), p) for p in paths]
    return max(choices, key=lambda pair: (pair[0][0], -pair[0][1], -pair[0][2]))


def solve(paths_at, first_outside, decode_outside, io_us, catalog, former):
    def pick(ppm):
        return select(paths_at(ppm), first_outside, decode_outside, io_us)

    def compact(choice):
        (margin, first, decode), path = choice
        return dict(
            first_final_s=float(first / MILLION),
            decode_s=float(decode / MILLION),
            decode_tok_s=float(47 * MILLION / decode),
            joint_margin_ms=float(margin / 1000),
            witness_sha256=register(path, catalog),
            on_original_frontier=history(path) in former,
        )

    best = pick(MILLION)
    minimum = None
    witness = None
    if best[0][0] >= 0:
        lo, hi = 0, MILLION
        while lo < hi:
            mid = (lo + hi) // 2
            if pick(mid)[0][0] >= 0:
                hi = mid
            else:
                lo = mid + 1
        minimum = lo
        selected = pick(lo)
        need(selected[0][0] >= 0 and (lo == 0 or pick(lo - 1)[0][0] < 0), "least joint exposure")
        witness = compact(selected)
    return dict(minimum_exposed_ppm=minimum, at_minimum=witness, at_full_exposure=compact(best))


def graphs(family, lookup, cut):
    ref = G["read"](HERE / "result.json", HTTP["NATIVE"]["REVIEW"])
    marks = {}
    for arm in ("FILTER", "FIXED", "SERIAL"):
        marks[arm], boundary = AUDIT["ticks"](family / arm, 2)
        need(boundary == cut and len(marks[arm]) == 47, "same nominal first-final sample")
    single = [dict(at=i + 1, emitted=1, proposal=[]) for i in range(46)]
    serial = ENV["priced"]("SERIAL", single, marks["SERIAL"], cut)
    variants = []
    for arm, tag in (("FILTER", "ON"), ("FIXED", "OFF")):
        plan = G["read"](lookup / tag / "proposals.json", ref["raw_digests"][tag])
        variants.extend(ENV["priced"](arm, plan["T2"], marks[arm], cut))
    return {
        "serial_reference": serial + [e for e in variants if e.block],
        "all_observed_serial": serial + variants,
    }, marks["SERIAL"]


def original_paths(prior, edges, n, cut):
    keys = {(e.start, e.end, e.arm, e.block): e for e in edges}
    paths = [
        tuple(keys[g["start"], g["end"], g["arm"], g["block"]] for g in w["groups"])
        for w in prior["witnesses"]
    ]
    need(
        len(edges) == prior["edges"]
        and [history(p) for p in ENV["frontier"](edges, n, cut)] == [history(p) for p in paths],
        "reproduced the prior Pareto frontier",
    )
    return paths


def checked_frontiers(edges, hits, cut, old, old_prices):
    @cache
    def paths_at(ppm):
        return ENV["frontier"](repriced(edges, hits, ppm, cut), 46, cut)

    need([history(p) for p in paths_at(0)] == [history(p) for p in old], "zero service control")
    for p, rec in zip(old, old_prices, strict=True):
        early, total = ENV["clocks"](p)
        after, last = ENV["clocks"](repriced(p, hits, MILLION, cut))
        for k, x in (
            ("max_early_ns", (early - after) * 1000),
            ("max_decode_ns", (total - last) * 1000),
        ):
            charged = rec["prefill"]["no_rescue"][k]
            need(0 <= charged - x < len(p), "fixed-witness check against rounded-up nanoseconds")
    return paths_at


def study(a):
    commit, tree = G["tree"](G["REPO"])
    need(
        commit == a.commit and AUDIT["sha"](HERE / "joint-protocol.md") == METHOD,
        "frozen joint test",
    )
    prior = G["read"](HERE / "envelope-result.json", BANK["ENVELOPE"])
    prices = G["read"](HERE / "bank-result.json", PRICES)
    lookup = G["read"](BANK["MIX"]["HERE"] / "receipt.json", BANK["BANKS"])
    ref = G["read"](HERE.parent / "reload-result.json", ENV["RELOADS"])
    schedule = G["read"](HERE.parent / "slot-result.json", ENV["SLOTS"])
    physical = G["read"](HERE / "http-result.json", prior["four_arm_review_sha256"])
    HTTP["R"]["reopen"](a.family, physical["family_sha256"])
    control = fixture()
    calls, rereads, matched = BANK["generations"](a, ref, schedule)
    banks = BANK["selection"](a, lookup)
    edges, marks = graphs(a.family, a.lookup_run, 44)
    orig = prior["turns"]["T2"]["scenarios"]
    old = {k: original_paths(orig[k], es, 46, 44) for k, es in edges.items()}
    row = physical["arms"]["SERIAL"]["rows"][1]

    def microseconds(field):
        return Fraction(str(row[field])) * MILLION

    first = microseconds("first_final_s") - microseconds("prefill_s") - (marks[44] - marks[0])
    decode = microseconds("decode_s") - (marks[-1] - marks[0])
    volume = prior["serial_nominal_prefill"]["read_bytes"]["min"]
    paths, scenarios = {}, {}
    for bank, keys in banks.items():
        pre = {k for k, c in calls.items() if c <= 2 and (k[0], k[3]) in keys}
        hits = Counter(c for k, c in calls.items() if c >= 3 and (k[0], k[3]) in keys)
        scenarios[bank] = {}
        for label, graph in edges.items():
            fixed = prices["scenarios"][bank]["witnesses"][label]
            paths_at = checked_frontiers(graph, hits, 44, old[label], fixed)
            former = {history(p) for p in old[label]}
            out = {}
            for profile, extra in (
                ("no_rescue", set()),
                ("matched35", matched),
                ("all230", rereads),
            ):
                union = len(pre | extra)
                need(
                    all(r["prefill"][profile]["union"] == union for r in fixed),
                    "same prefill union",
                )
                floor = Fraction(max(0, volume - union * WINDOW) * MILLION, RATE)
                out[profile] = dict(
                    union=union,
                    min_prefill_service_s=float(floor / MILLION),
                    **solve(paths_at, first, decode, floor, paths, former),
                )
            scenarios[bank][label] = out
    return dict(
        status="TRACE_DERIVED_CACHE_AWARE_JOINT_FRONTIER",
        commit=commit,
        tree=tree,
        method_sha256=METHOD,
        fixed_paths_sha256=PRICES,
        envelope_sha256=BANK["ENVELOPE"],
        new_model_starts=0,
        new_requests=0,
        fixture_pass=control,
        paths=paths,
        scenarios=scenarios,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("archive", "family", "lookup-run", "capture", "verified", "plan", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    save(a.new_output_dir / "result.json", study(a))
