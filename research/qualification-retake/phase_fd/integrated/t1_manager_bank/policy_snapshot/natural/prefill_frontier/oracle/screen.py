"""Paid grouped paging on the original and reconstructed carry cuts of the same nominal T2."""

import argparse
import hashlib
import json
import os
import resource
import signal
import subprocess
from itertools import combinations, pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
F = HERE.parent
N = F.parent
INTEGRATED = N.parents[2]
R = N / "replay"
front = run_path(F / "screen.py")
check, pinned, sha = (front[k] for k in ("check", "pinned", "digest"))
FRONTIER = "5225590f4a5ea17f7faa1d13fede10dc9abc771d53dbc388333709a4d86765c2"
PLAN = "aed09397a16ed706365d73e0d2535427528476b41d66e3d5e43ad90da345d79a"
PART65 = "1713b1e73b8e59c34b1f12fc268a9d6caafba09d5c82707476ec9a0febd0069b"
QUAL = INTEGRATED.parents[1]
CUTS = INTEGRATED / "tile_boundary_floor/cuts.py"
ORACLE = INTEGRATED / "t1_primary_victim/oracle.py"
METHODS = {
    CUTS: "4f4da5733ea7627e2fcd57a6b84bd6c4ed47b8379d064885e92c0fe9c05d5b27",
    ORACLE: "b655c173fb9dce5264e105adcd9abf6f433a9dfad4dba93760b7f22364cdf023",
    QUAL / "cache_bound.py": "7a1eca13746bac6a2f0b2a989040374e801d0e058d58240d022b80ddb07b4e46",
    R / "screen.py": "c60861939a385fa6ff85d38840ca5255ea64bce4fbca45d195fe876de07ddd51",
    R / "manager.py": "ceaa386d3d5994dd02ebc98d148378405bbf0fa46e98e06fd46a3cd48d44a05f",
    F / "screen.py": "a61f52ce1c310d54ae87fad5e3f16c656cc2ef47d423d6fe9f0dad547ce4f9ea",
}


def fingerprint(obj):
    return hashlib.sha256(
        json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def snapshot(manager):
    check(
        all(not p.possible_loading and p.next_wave == p.next_count for p in manager.pools),
        "undrained model cut",
    )
    members = [set(p.ids) for p in manager.pools]
    check(all(len(s) == 40 and -1 not in s for s in members), "invalid full member set")
    return members


def carry_inputs(replay, groups, slots, words, calls, interval, tags, history, plan, geometry):
    mgr = replay["Manager"](slots, words, calls, interval, tags)
    snaps = []
    ranks = None
    sites = iter(plan["groups"])
    own_cells = [[[] for _ in range(36)] for _ in range(6)]
    counts = {(stage, tier): 0 for stage in ("prefill", "decode") for tier in ("cpu", "cuda")}
    begin, first = groups[0]["site"][0], True
    previous_tile = None
    terminal = None
    for group in groups:
        call, tile, layer, wave = site = group["site"]
        pf = call < begin + 2
        if pf and previous_tile != (call, tile):
            check(geometry[len(snaps)] == (call, tile), "tile grid")
            snaps.append(snapshot(mgr))
            previous_tile = (call, tile)
        if not pf and first:
            snaps.append(snapshot(mgr))
            terminal = fingerprint(
                {
                    "calls": mgr.calls,
                    "pools": [
                        [p.ids, p.gen, p.ages, p.heat, p.clock, p.parking] for p in mgr.pools
                    ],
                }
            )
            first = False
        if wave in (-1, 0):
            ranks = group["ranks"]
        else:
            check(not group["ranks"], "duplicate vector")
        check(len(ranks) == 4 * group["rows"], "missing ranks")
        alloc, demands = mgr.callback(layer, wave, ranks)
        ids = [e for e, _, _ in demands]
        check(ids == [e for e, _, _ in group["demands"]], "logical DEMAND changed")
        phase = "prefill" if pf else "decode"
        counts[phase, "cpu" if layer < 25 else "cuda"] += sum(
            e not in tags[layer] for e, *_ in alloc
        )
        if pf and ids:
            own_cells[len(snaps) - 1][layer].append(ids)
        if not pf:
            row = next(sites)
            check(tuple(row[k] for k in ("call", "tile", "layer", "wave")) == site, "decode site")
            check(
                [(x["expert"], x["slot"], x["generation"], x["source"]) for x in row["jobs"]]
                == [(e, s, g, "bank" if e in tags[layer] else "disk") for e, s, g, _, _ in alloc],
                "full decode plan and allocation identities",
            )
    check(
        next(sites, None) is None and len(plan["groups"]) == 46 * 36 and len(snaps) == 7, "coverage"
    )
    check(
        mgr.emitted.hexdigest()
        == history["carry"]["inferred_slot_stream_sha256"]
        == plan["causal_slot_stream_sha256"]
        and dict(mgr.proofs) == history["carry"]["induction"],
        "complete carry slot stream/induction",
    )
    static = history["carry"]["variants"]["bank"]
    check(all(n == static[p][t]["disk_jobs"] for (p, t), n in counts.items()), "causal costs")
    return own_cells, snaps, terminal


def enumerate_cuts(cells, snap, backed, n_slots, paid):
    """Cost of each required interval endpoint. The last endpoint can alternatively be free."""
    length = len(cells)
    check(length >= 2 and len(snap) == length + 1, "cut count")
    intervals = {}
    for lo in range(length):
        for hi in range(lo + 1, length + 1):
            for final in (False, True) if hi == length else (True,):
                result = []
                for layer, bank in enumerate(backed):
                    waves = [g for cell in cells[lo:hi] for g in cell[layer]]
                    if final:
                        waves.append(sorted(snap[hi][layer]))
                    result.append(paid(waves, n_slots, snap[lo][layer], bank))
                intervals[lo, hi, final] = result

    def price(cuts, terminal=True):
        endpoints = [0, *sorted(cuts), length]
        costs = [intervals[a, b, terminal if b == length else True] for a, b in pairwise(endpoints)]
        return [sum(x) for x in zip(*costs, strict=True)]

    interior = tuple(range(2, length))
    output = {}
    for n in range(len(interior) + 1):
        for released in combinations(interior, n):
            fixed = {1, *interior} - set(released)
            amount = price(fixed)
            output[released] = amount
            for r in released:
                earlier = output[tuple(x for x in released if x != r)]
                check(all(a <= b for a, b in zip(amount, earlier, strict=True)), "monotonic cuts")
    cases = dict(
        all_sets_fixed=output[()],
        external_sets_fixed=output[interior],
        return5_fixed_terminal_free=price({1}, False),
        only_terminal_fixed=price(set()),
        no_required_exit=price(set(), False),
    )
    for key in ("external_sets_fixed", "only_terminal_fixed"):
        other = (
            "return5_fixed_terminal_free" if key == "external_sets_fixed" else "no_required_exit"
        )
        check(
            all(a >= b for a, b in zip(cases[key], cases[other], strict=True)),
            "terminal restoration",
        )
    return output, cases


def aggregate(array):
    return dict(cpu=sum(array[:25]), cuda=sum(array[25:]), all=sum(array))


def price(n, frontier):
    volume = n * front["PAYLOAD"]
    rows = {}
    for order, old in frontier["pack_orders"].items():
        budget = frontier["budget_prefill_plus_decode_ns"] - old["conditional_decode_ns"]
        gap, floor = (frontier["gaps"][x] for x in ("total_ns", "protected_ns"))
        costs = front["frontier"](volume, budget, gap, floor)
        rows[order] = dict(
            prefill_budget_ns=budget,
            largest_jobs_serial=(budget - gap) * front["BANDWIDTH"] // (10**9 * front["PAYLOAD"]),
            largest_jobs_pipeline=(budget - floor)
            * front["BANDWIDTH"]
            // (10**9 * front["PAYLOAD"]),
            min_useful_serial_Bps=costs["minimum_useful_Bps_serial"],
            min_useful_pipeline_Bps=costs["minimum_useful_Bps_optimistic_pipeline"],
            serial_margin_ns=costs["serial_margin_ns"],
            optimistic_pipeline_margin_ns=costs["optimistic_pipeline_margin_ns"],
        )
    return rows


def run(archive):
    check(all(sha(p) == h for p, h in METHODS.items()), "method identity")
    hist = run_path(INTEGRATED / "tile_boundary_floor/cuts.py")
    paid = run_path(INTEGRATED / "t1_primary_victim/oracle.py")["paid_minimum"]
    replay = run_path(R / "screen.py")
    frontier = pinned(F / "evidence/receipt.json", FRONTIER)
    seals = frontier["origins"]
    a, b = archive / "part-63", archive / "part-65"
    p63 = pinned(a / "manifest.json", seals["archive63"])["files"]
    p65 = pinned(b / "manifest.json", PART65)["files"]
    rel = "tesy-decode-transport-prepare-20261125-r01/plan.json"
    check(
        p65[rel]["sha256"] == PLAN
        and p63[front["FAMILY_NAME"] + "/ON/raw/events.pfj"]["sha256"] == seals["journal"],
        "archives",
    )
    plan = pinned(b / rel, PLAN)
    family = a / front["FAMILY_NAME"]
    rows, slots, words, calls, interval, tags, bases, origin = replay["sources"](
        family, seals["family"]
    )
    history = pinned(a / "tesy-policy-natural-replay-20261125-r02/receipt.json", seals["replay"])
    check(
        all(history[k] == v for k, v in origin.items()) and sum(map(len, tags)) == 353,
        "reconstructed seal and bank",
    )
    groups, reads, work = replay["segment"](rows)
    widths = [[r.a for r in rows if r.kind == 3 and r.call == c] for c in (74, 75)]
    check(
        work == history["observed"] and widths == [[5], [32, 32, 32, 32, 20]], "native population"
    )
    _, old = replay["trajectory"](
        groups,
        reads,
        slots,
        words,
        calls,
        interval,
        tags,
        bases,
        priority=False,
        restore=False,
        reference=None,
    )
    check(old == history["r0"], "R0 numerical control replay")
    all_rows, header = replay["fd"].read_journal(family / "ON/raw/events.pfj")
    check(header["journal_sha256"] == seals["journal"], "journal")
    observed, r0 = hist["observed"](all_rows)
    cells, carry, hash_terminal = carry_inputs(
        replay, groups, slots, words, calls, interval, tags, history, plan, hist["base"]["GEOMETRY"]
    )
    check(cells == observed[:6] and r0[0] == carry[0], "waves/initial identity")
    scenarios = {}
    for label, snaps in (("r0", r0), ("carry", carry)):
        subsets, cases = enumerate_cuts(cells, snaps, tags, 40, paid)
        witness = history[label]["variants"]["bank"]["prefill"]
        by_tier = aggregate(cases["all_sets_fixed"])
        check(all(by_tier[t] <= witness[t]["disk_jobs"] for t in ("cpu", "cuda")), "causal witness")
        values = {k: aggregate(v) for k, v in cases.items()}
        prices = {k: price(v["all"], frontier) for k, v in values.items()}
        terminal_costs = {
            key: values[fixed]["all"] - values[free]["all"]
            for key, fixed, free in (
                ("return5_fixed", "external_sets_fixed", "return5_fixed_terminal_free"),
                ("return5_free", "only_terminal_fixed", "no_required_exit"),
            )
        }
        scenarios[label] = dict(
            cuts=[
                dict(released_after_tiles=[v - 1 for v in subset], **aggregate(arr))
                for subset, arr in subsets.items()
            ],
            cases=values,
            conditional_prices=prices,
            extra_minimum_for_terminal=terminal_costs,
            resident_set_sha256=[fingerprint([sorted(s) for s in sets]) for sets in snaps],
            fixed_bank_causal_witness=sum(witness[t]["disk_jobs"] for t in ("cpu", "cuda")),
        )
    check(
        scenarios["r0"]["cases"]["no_required_exit"]
        == scenarios["carry"]["cases"]["no_required_exit"],
        "unconstrained endpoint depends on outcome",
    )
    return dict(
        status="REPRODUCED_R02_OFFLINE_40_SLOT_PREFILL_FLOORS",
        source_seals=seals,
        frontier_sha256=FRONTIER,
        part65_manifest_sha256=PART65,
        plan_sha256=PLAN,
        carry_reconstructed_terminal_policy_sha256=hash_terminal,
        arms=scenarios,
        carry_only_members_by_boundary=[
            sum(len(c - r) for c, r in zip(a, b, strict=True))
            for a, b in zip(carry, r0, strict=True)
        ],
        tile_widths=widths,
        demand_groups_by_tile=[sum(len(x) for x in cell) for cell in cells],
        physically_loaded_weights=0,
        model_forwards=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    try:
        signal.alarm(120)
        resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))
        git = ["git", "-C", str(HERE), "-c", "core.preloadIndex=false", "-c", "index.threads=1"]
        check(not subprocess.check_output([*git, "status", "--porcelain"]), "dirty checkout")
        result = run(a.archive)
        result.update(
            commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
            program_sha256=sha(Path(__file__)),
            protocol_sha256=sha(HERE / "protocol.md"),
        )
    except Exception as e:
        result = {"status": "FAIL_PRESERVED", "reason": f"{type(e).__name__}: {e}"}
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
