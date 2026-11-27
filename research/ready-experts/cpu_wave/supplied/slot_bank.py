"""Reprice necessary and constructed schedules for a bank chosen from past references."""

import argparse
import gzip
import hashlib
import json
import os
import subprocess
from collections import Counter, defaultdict
from dataclasses import replace
from functools import cache
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
LIFE = run_path(HERE / "slot_lifetime.py")
need, sha, limits = (LIFE[k] for k in ("need", "sha", "limits"))
METHOD = "6d8ed17b01d6710b0b8244d9d4e964205e6559e5d18b47d26c50b034668d6dc1"
SLOTS = "b024b4dbcb93690fe17864815a591f7a508b0c2d0e55c45f2af6be9b9bd48739"
INTERVALS = "fe40b730da54e0e675619ff947735b5618a66ec087ecb4b4dcf1dc5fa2210f15"


def bank(iv, archived, tx, primary, seed, counts, proof):
    seed = [key for key in seed if key not in primary]
    hits, costs, peak = iv["online"](tx, seed, counts, iv["CAP"])
    starts = iv["opportunities"](tx, seed)
    slots, _ = iv["assign"](starts, hits, iv["CAP"])
    iv["audit"](tx, seed, starts, slots, iv["CAP"])
    historical = archived["results"]["frequency"]
    need([[starts[i], i, slots[i]] for i in sorted(hits)] == proof, "different hit or supplier")
    need(
        len(seed) == archived["initial_secondary"]
        and len(hits) == historical["all_hits"]
        and peak == historical["peak"] == iv["CAP"],
        "bank capacity or online accounting",
    )
    for tier, c in costs.items():
        expected = historical["payload_by_tier"][tier]
        for op in ("promotions", "captures"):
            need(
                c[op] == expected[op] and c[op] * iv["PAYLOAD"] == expected[op + "_payload_bytes"],
                "uncharged banking traffic",
            )
    return hits


def graph_cases(rows, src, co, placed, archive_grant):
    host = src["NATIVE"]["host_trace"](rows)
    waves, _ = src["timeline"](rows)
    by_call = defaultdict(list)
    for w in waves:
        by_call[w.site[0]].append(w)
    sizes = {src["origin"](r): r.a for r in rows if r.kind == 9}
    controls, detail = co["graph_credits"](rows, placed, archive_grant)
    result, done = {}, Counter()
    for c in host["calls"]:
        n = c["number"]
        ws = by_call[n]
        entry = ws[0].start - c["enter_ns"]
        gaps = [
            b - w.end for w, b in zip(ws, [w.start for w in ws[1:]] + [c["return_ns"]], strict=True)
        ]
        credits = []
        for w, gap in zip(ws, gaps, strict=True):
            layer, wave = w.site[2:]
            eligible = (
                n <= 2 and layer < 25 and not w.demands and (sizes[w.site], layer, wave) in placed
            )
            credits.append(gap if eligible else 0)
            if eligible:
                done.update(waves=1, ns=gap)
        result[n] = (
            entry,
            {
                "observed": gaps,
                "empty_wave_grant": [g - x for g, x in zip(gaps, credits, strict=True)],
            },
        )
    conserved = detail["placed"]
    need(
        done["waves"] == conserved["waves"] == 711
        and done["ns"]
        == conserved["inside_ns"] + conserved["edge_ns"]
        == sum(sum(c.values()) for c in controls["placed"].values()),
        "eligible graph credit",
    )
    return result, dict(done)


def intervention(jobs, starts, hits, ranked, policy, read_percent):
    chosen = []
    for j in jobs:
        hit = j.order + 1 in hits
        use_history = policy == "history_four" and j.key[3] in ranked[j.key[0]]
        opening = j.horizon if policy == "two_oracle" or use_history else starts[j.region]
        read = 0 if hit else (j.read * read_percent + 99) // 100
        chosen.append(replace(j, read=read, horizon=j.reserve if hit else opening))
    return chosen


def prices(calls, starts, graphs, exterior, hits, ranked, policy, pct, *, witness):
    clocks = {
        g: dict(floor=exterior.copy(), schedule=exterior.copy())
        for g in ("observed", "empty_wave_grant")
    }
    docs = {g: hashlib.sha256() for g in clocks}
    for n, original in calls.items():
        jobs = intervention(original, starts[n], hits, ranked, policy, pct)
        entry, alternatives = graphs[n]
        edges = LIFE["interval_edges"](jobs, len(alternatives["observed"]))
        for g, gaps in alternatives.items():
            cell = clocks[g]
            lower = LIFE["graph_floor"](entry, gaps, edges, 100)
            LIFE["add_time"](cell["floor"], n, lower)
            if witness:
                path = LIFE["schedule"](jobs, entry, gaps)
                LIFE["audit"](jobs, entry, gaps, path)
                transport = path[0][-1]
                need(lower <= transport, "constructed schedule shorter than necessary service")
                LIFE["add_time"](cell["schedule"], n, transport)
                docs[g].update(json.dumps(path, separators=(",", ":")).encode() + b"\n")
    if witness:
        for g, cell in clocks.items():
            cell["decision"] = LIFE["decision"](cell["floor"], cell["schedule"])
            cell["schedule_sha256"] = docs[g].hexdigest()
    return clocks


def read_cut(price):
    def fits(v):
        return all(v[k] <= cap for k, cap in limits.items())

    if fits(price(100)):
        return dict(min_saving_percent=0, fits_ns=price(100))
    if not fits(price(0)):
        return dict(min_saving_percent=None, free_read_floor_ns=price(0))
    lo, hi = 0, 100
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if fits(price(mid)):
            lo = mid
        else:
            hi = mid
    return dict(
        min_saving_percent=100 - lo, fits_ns=price(lo), one_percent_less_saving_ns=price(hi)
    )


def regional_cut(calls, starts, graphs, exterior, hits, ranked):
    @cache
    def cost(pct):
        table = prices(calls, starts, graphs, exterior, hits, ranked, "region", pct, witness=False)
        return table["empty_wave_grant"]["floor"]

    return read_cut(cost)


def run(archive, renewal, plan):
    need(
        sha(HERE / "slot-bank.md") == METHOD and sha(HERE / "slot-lifetime.json") == SLOTS,
        "method or slot evidence",
    )
    old = json.loads((HERE / "slot-lifetime.json").read_bytes())
    need(sha(HERE / "slot_lifetime.py") == old["source_sha256"], "changed lifetime implementation")
    screen = run_path(HERE.parents[1] / "screen.py")
    src = screen["SOURCE"]
    primary = run_path(screen["HERE"] / "primary/replay.py")
    co, iv = primary["CO"], primary["IV"]
    history = src["pinned"](renewal / "intervals/receipt.json", INTERVALS)
    proofpath = renewal / "intervals/schedule.json.gz"
    need(sha(proofpath) == history["schedule_sha256"], "bank proof identity")
    proof = json.loads(gzip.decompress(proofpath.read_bytes()))["frequency"]
    placed = co["placements"](renewal / "placement")
    grants = src["pinned"](co["LOOKUP"] / "empty-result.json", co["EMPTY_RESULT"])
    previous = src["pinned"](
        screen["NATURAL"] / "prefill_retention/request_cost/receipt.json", screen["PRIOR"]
    )
    f = LIFE["FR"]
    sealed = f["train"](screen, archive)
    frontier = src["pinned"](HERE / "frontier.json", run_path(HERE / "composition.py")["PARENT"])
    need(
        sha(plan) == frontier["plan_sha256"] and json.loads(plan.read_bytes()) == sealed,
        "T1-only predictor",
    )
    root = archive / "part-106" / src["SOURCES"]["P106"][0]
    counts, cut = iv["train"](root / "ON")
    need(
        cut == history["t1_prefix_sha256"] and counts.total() == history["t1_reservations"],
        "bank T1 cutoff",
    )
    banks, rows106, _, _ = src["Q"]["read_new"](root, src["SOURCES"]["P106"][1])
    seed = list(map(tuple, banks["banks"]["lru"]["ordered_keys"]))
    traces = {}
    for label in ("P97", "P106"):
        rows = rows106
        if label == "P97":
            path = archive / "part-97" / src["SOURCES"][label][0] / "ON/raw/events.pfj"
            rows, _ = src["T"]["PFJ"]["read_journal"](path)
        (_, exterior), tx, initial, _, _, lineage = iv["load_arm"](
            archive, label, rows, seed, previous[label]
        )
        parent = old["traces"][label]
        need(
            list(lineage) == history["routing_and_reservations"]
            and exterior == parent["exterior_ns"],
            "different jobs or clocks",
        )
        hits = bank(iv, history, tx, initial, seed, counts, proof)
        calls, regions, population = LIFE["ledger"](rows, src, primary)
        need(dict(population) == parent["population"], "slot replay population")
        starts = {
            n: {reg: i for i, reg in enumerate(seq) if not i or seq[i - 1] != reg}
            for n, seq in regions.items()
        }
        miss = Counter()
        for n, jobs in calls.items():
            for j in jobs:
                need(tx[j.order].generation == j.key, "wrong bank transaction")
                if j.order + 1 not in hits:
                    miss[screen["phase"](n)] += 1
        need(sum(miss.values()) + len(hits) == len(tx), "miss/hit conservation")
        graphs, grant = graph_cases(rows, src, co, placed, grants["journals"][label])
        cases = {}
        for bank_name, actual in (("unused", set()), ("frequency", hits)):
            cases[bank_name] = {
                policy: prices(
                    calls,
                    starts,
                    graphs,
                    exterior,
                    actual,
                    sealed["ranked"],
                    policy,
                    100,
                    witness=True,
                )
                for policy in ("region", "history_four", "two_oracle")
            }
        control = cases["unused"]["two_oracle"]["observed"]
        need(
            control["floor"] == parent["regimes"]["paid_graph"]["floor_ns"]
            and control["schedule"] == parent["regimes"]["paid_graph"]["schedule_ns"],
            "independent no-bank wave clocks",
        )

        traces[label] = dict(
            regimes=cases,
            read_cut=regional_cut(calls, starts, graphs, exterior, hits, sealed["ranked"]),
            grant=grant,
            misses=dict(miss),
            journal_sha256=parent["journal_sha256"],
        )
    return dict(
        classification="SIMULATED_CONDITIONAL",
        protocol_sha256=METHOD,
        source_sha256=sha(Path(__file__)),
        parent_sha256=SLOTS,
        bank_sha256=INTERVALS,
        bank_proof_sha256=sha(proofpath),
        t1_prefix_sha256=cut,
        plan_sha256=sha(plan),
        hits=len(proof),
        bank=history["results"]["frequency"]["payload_by_tier"],
        capacity=iv["CAP"],
        initial_secondary=history["initial_secondary"],
        traces=traces,
        model_forwards=0,
        gpu_forwards=0,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for opt in ("archive", "renewal", "plan", "new-output-dir"):
        parser.add_argument("--" + opt, type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir()
    try:
        git = ["git", "-c", "core.preloadIndex=false", "-c", "index.threads=1"]
        refs = subprocess.check_output(
            [*git, "rev-parse", "HEAD", "HEAD^{tree}"], cwd=HERE, text=True
        ).splitlines()
        provenance = dict(
            commit=refs[0], tree=refs[1], program_sha256=sha(Path(__file__)), protocol_sha256=METHOD
        )
        (args.new_output_dir / "provenance.json").write_text(
            json.dumps(provenance, indent=2) + "\n"
        )
        need(
            not subprocess.check_output([*git, "status", "--porcelain"], cwd=HERE),
            "unclean replay tree",
        )
        record = run(args.archive, args.renewal, args.plan)
    except Exception as exc:
        raw_roots = (args.archive.resolve(), args.renewal.resolve())
        missing = (
            isinstance(exc, FileNotFoundError)
            and exc.filename
            and any(
                Path(exc.filename).resolve().is_relative_to(root)
                for root in (*raw_roots, args.plan.resolve())
            )
        )
        record = dict(
            classification="NOT_RUN_RAW_REQUIRED" if missing else "FAIL_PRESERVED", reason=str(exc)
        )
    tmp = args.new_output_dir / ".receipt.tmp"
    with tmp.open("x") as f:
        json.dump(record, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    tmp.rename(args.new_output_dir / "slot-bank.json")
    print(record["classification"], record.get("reason", ""))
    raise SystemExit(record["classification"] != "SIMULATED_CONDITIONAL")
