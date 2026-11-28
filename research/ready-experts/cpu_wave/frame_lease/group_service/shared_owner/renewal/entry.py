"""Replay the compiled CPU bank across both nominal turns and recover the first consumers."""

import argparse
import gzip
import hashlib
import json
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
H = HERE.parents[1]
A = run_path(H / "address.py")
L, V, need, sha = (A[k] for k in ("L", "V", "need", "sha"))
G, F = A["G"], A["F"]
METHOD = "2e960f8a1408f5148dc0ca1eee479d3e0d64461e75b24348073e3c7c1d1a9d35"
P106 = "cb13ff990afb3164bb61086e57a6caeff14187b66a1784c88e79cd3d521121bd"
P97 = "05e32c2af753026e471fa61c9dcb43867ca6b9a3001045a2138bc96c422928dc"
PREFIX = "16574f71e2a697479d1be118ddd5d5a103b3218c1f48b428ee32ebbb355fe259"
PAYLOAD = A["T"]["PAYLOAD"]
WINDOW = F["WINDOW"]


def digest(value):
    return hashlib.sha256(L["encode"](value)).hexdigest()


def tx(row, shift=0):
    return [row.call - shift, row.tile, row.layer, row.slot, row.gen, row.expert, row.a]


def snapshot(rows):
    initial = sorted(
        [r.layer, r.slot, r.expert, r.gen] for r in rows if r.kind == 5 and r.layer < 25
    )
    need(
        len(initial) == 1000 and len({(l, s) for l, s, _, _ in initial}) == 1000,
        "CPU primary cardinality",
    )
    return initial


def capture(archive):
    src = run_path(HERE.parents[4] / "selection.py")
    pf = src["PROFILE"]
    raw = archive / "part-106" / src["SRC"]["SOURCES"]["P106"][0] / "ON"
    old = archive / "part-97" / src["SRC"]["SOURCES"]["P97"][0] / "ON/raw/events.pfj"
    new = raw / "observer/events.pfj"
    seal = F["SRC"]["pinned"](raw / "before-t2.json", src["T1_SEAL"])
    need(sha(new) == P106 and sha(old) == P97 and seal["sha256"] == PREFIX, "unverified journal")
    cut, count = pf["metadata"](new, True)
    need(cut == seal["records"], "T1 cut")
    rows = list(pf["iter_rows"](new, 0, cut))
    verified, end = pf["prefix_grade"](rows, pf["T1"], 9)
    need(all(seal[k] == v for k, v in verified.items()), "unverified causal prefix")
    need(all((r.a, r.b) in ((0, 0), (2, 0)) for r in rows if r.kind == 5), "pending at entry")
    initial, prefix = snapshot(rows), [tx(r) for r in rows if r.kind == 11]
    final_t1 = sorted(
        [l, s, e, g] for (l, s), (e, g, state) in end.items() if l < 25 and state == 2
    )
    tail = list(pf["iter_rows"](new, cut, count - cut))
    old_rows, header = pf["PFJ"]["read_journal"](old)
    need(
        header["journal_sha256"] == P97 and final_t1 == snapshot(tail) == snapshot(old_rows),
        "T2 entry",
    )
    tx2 = [tx(r, seal["calls"]) for r in tail if r.kind == 11]
    need(tx2 == [tx(r) for r in old_rows if r.kind == 11], "two T2 reservation orders")

    def end_state(raw):
        slots = {(l, s): (e, g) for l, s, e, g in final_t1}
        for r in raw:
            if r.kind == 17 and r.layer < 25:
                slots[r.layer, r.slot] = (r.expert, r.gen)
        return sorted([l, s, e, g] for (l, s), (e, g) in slots.items())

    final = end_state(tail)
    need(final == end_state(old_rows), "different published final T2")
    return dict(
        initial=initial,
        prefix=prefix,
        at_post=final_t1,
        terminal=final,
        suffix_sha256=digest(tx2),
        qualified_positions=[seal["first_position"], seal["last_position"]],
        prefix_records=cut,
        prefix_calls=seal["calls"],
        prefix_pfj_sha256=PREFIX,
        journal_sha256=dict(P97=P97, P106=P106),
    )


def reserve(pool, frequency, serial, layer, expert, victim):
    k = layer, expert
    frequency[k] += 1
    hit = pool.pop(k, None) is not None
    captured = False
    if victim >= 0:
        old = layer, victim
        need(old not in pool and old != k, "resident secondary/primary duplicate")
        rank = (frequency[old], serial)
        if len(pool) == 252:
            cold = min(pool, key=pool.__getitem__)
            if pool[cold] < rank:
                del pool[cold]
        if len(pool) < 252:
            pool[old] = rank
            captured = True
    return hit, captured


def execute(exe, w, second):
    slots = {(l, s): (e, g) for l, s, e, g in w["initial"]}
    lines = [f"S {l} {s} {g} {e}" for l, s, e, g in w["initial"]]
    pool, frequency, expected, groups = {}, Counter(), {}, {}
    offset = len(w["prefix"])

    def frozen():
        return sorted([l, s, e, g] for (l, s), (e, g) in slots.items())

    for turn, rows in enumerate((w["prefix"], second), 1):
        for i, (call, tile, l, s, g, e, old) in enumerate(rows):
            if l >= 25:
                continue
            ix = i if turn == 1 else offset + i
            need(slots[l, s] == (old, g - 1), "reference lineage")
            slots[l, s] = e, g
            lines.append(f"R {ix} {l} {s} {g} {e} {old}")
            h, c = reserve(pool, frequency, ix, l, e, old)
            expected[ix] = (int(h), int(c), len(pool))
            groups[ix] = (
                ("T1_prefill" if call <= 9 else "T1_decode") if turn == 1 else L["phase"](call)
            )
        if turn == 1:
            entry_occupancy = len(pool)
        need(
            frozen() == w["at_post" if turn == 1 else "terminal"], "unmatched primary publications"
        )
    phases = defaultdict(Counter)
    population = set()
    enc = ("\n".join(lines) + "\n").encode()
    signature = {}
    for role in ("id", "copy"):
        result = subprocess.run(
            [exe, "--replay-" + role], input=enc, capture_output=True, check=True, timeout=15
        )
        signature[role] = hashlib.sha256(result.stdout).hexdigest()
        rows = [list(map(int, x.split())) for x in result.stdout.splitlines()]
        need([r[0] for r in rows] == list(expected), "accepted native population")
        for ix, hit, captured, source, target, staged, occupied in rows:
            need(
                expected[ix] == (hit, captured, occupied)
                and bool(hit) == (source >= 0)
                and -1 <= source < 1252
                and 0 <= target < 1252
                and staged in (0, 1),
                "native vs independent reference",
            )
            p = phases[groups[ix]]
            if role == "id":
                need(not staged and (not hit or source == target), "ID materialized")
                p.update(reservations=1, hits=hit, captures=captured, misses=1 - hit)
                if ix >= offset and hit:
                    population.add(ix - offset)
            else:
                need(bool(staged) == bool(hit and source == target), "wrong staging reference")
                p["staged_copy_hits"] += staged
    for value in phases.values():
        value.update(
            disk_requested_B=value["reservations"] * WINDOW,
            bank_requested_B=value["misses"] * WINDOW,
            id_weight_sets=3 * value["misses"],
            copy_weight_sets=3 * value["reservations"],
            copy_extra_SET_B=value["hits"] * PAYLOAD,
            copy_staging_B=value["staged_copy_hits"] * PAYLOAD,
        )
    return dict(
        phases=dict(phases),
        entry_occupancy=entry_occupancy,
        terminal_occupancy=len(pool),
        replay_sha256=signature,
    ), population


def assess(exe, w):
    need(
        sha(HERE / "entry-protocol.md") == METHOD
        and w["prefix_pfj_sha256"] == PREFIX
        and w["journal_sha256"] == dict(P97=P97, P106=P106),
        "unregistered input",
    )
    rows, prior = V["sources"]()
    need(
        digest(rows) == w["suffix_sha256"] and len(w["prefix"]) == 5727 and len(rows) == 2354,
        "sealed reservations",
    )
    bank, hits = execute(exe, w, rows)
    seed_hits = {i for i, (tier, src, dst) in enumerate(prior) if tier == 0 and src is not None}
    cases = F["SRC"]["pinned"](H / "evidence-20261128-r01/scenarios.json", A["PHYSICAL"])
    service = L["X"]["ORIGINAL"] / "service.json.gz"
    history = H.parent / "evidence-lifetime-20261128-r01"
    waves = history / "waves.json.gz"
    need(
        sha(service) == V["SERVICE"]
        and sha(waves)
        == F["SRC"]["pinned"](history / "decision.json", G["PRIOR"])["compressed_windows_sha256"],
        "original worker clocks",
    )
    journals = {}
    windows = F["unpack"](waves)
    for tag, native in F["unpack"](service).items():
        view, seen = A["first_consumers"](windows[tag], native)
        need(hits <= seen, "hit with no first consumer")
        phases = A["price"](view, native["jobs"], hits)
        named = {}
        for label, case in cases[tag].items():
            cut = [v for v in view if v[0] == case["site"]]
            need(len(cut) == 1, "registered barrier")
            prices = A["price"](cut, native["jobs"], hits)
            named[label] = dict(
                site=case["site"],
                expert=[j["expert"] for j in case["jobs"] if j["index"] in hits],
                **prices[L["phase"](case["site"][0])],
            )
        largest = {}
        for name in L["PHASES"]:
            candidates = [
                (len(first & hits), site, sorted(first & hits))
                for site, _, _, first in view
                if L["phase"](site[0]) == name
            ]
            if candidates:
                n, site, indices = max(candidates, key=lambda x: (x[0], [-i for i in x[1]]))
                largest[name] = dict(site=site, hits=n, expert=[rows[i][5] for i in indices])
        journals[tag] = dict(
            phases=phases,
            registered=named,
            largest_at_observed_barrier=largest,
            to_first={k: sum(phases[p][k] for p in L["PHASES"][:3]) for k in phases["tail"]},
        )
    go = all(
        len(j["registered"]["decode4"]["expert"]) == 4
        and j["registered"]["decode4"]["remove_read_and_sets"] > 0
        for j in journals.values()
    )
    return dict(
        status="GO_OBSERVED_DECODE_QUARTET" if go else "NO_GO_TRANSFER_REGISTERED_QUARTET",
        evidence="TRACE_DERIVED_SERIAL_POLICY_FIXED_JOURNAL_CLOCKS",
        **bank,
        initial_ready=sum(e >= 0 for l, s, e, g in w["initial"]),
        initial_empty=sum(e < 0 for l, s, e, g in w["initial"]),
        seed_hits=len(seed_hits),
        continuous_hits=len(hits),
        common_hits=len(hits & seed_hits),
        gained=len(hits - seed_hits),
        lost=len(seed_hits - hits),
        journals=journals,
        method=METHOD,
        witness_sha256=digest(w),
        terminal_sha256=digest(w["terminal"]),
        controller_sha256=sha(HERE / "cpu-weight-bank.h"),
        driver_sha256=sha(HERE / "check_bank.cpp"),
        model_forwards=0,
        weight_bytes_read=0,
        integrated_client_ns=None,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", type=Path)
    mode.add_argument("--new-output-dir", type=Path)
    p.add_argument("--archive", type=Path)
    p.add_argument("--controller", type=Path)
    a = p.parse_args()
    if a.new_output_dir and not a.archive:
        p.error("raw archive required")
    out = a.new_output_dir
    if out:
        out.mkdir(mode=0o700)
    try:
        witness = capture(a.archive) if a.archive else F["unpack"](a.check / "transactions.json.gz")
        raw = L["encode"](witness)
        with tempfile.TemporaryDirectory(prefix="tesy-bank-entry-") as tmp:
            exe = a.controller
            if exe is None:
                exe = Path(tmp) / "bank"
                subprocess.run(
                    ["c++", "-std=c++20", "-O2", HERE / "check_bank.cpp", "-o", exe],
                    check=True,
                    timeout=30,
                )
            subprocess.run([exe], check=True, timeout=8)
            result = assess(exe, witness)
        if out:
            with (out / "transactions.json.gz").open("xb") as f:
                f.write(gzip.compress(raw, mtime=0))
            temp = out / ".pending"
            temp.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
            temp.rename(out / "decision.json")
        else:
            need(
                raw == gzip.decompress((a.check / "transactions.json.gz").read_bytes())
                and result == json.loads((a.check / "decision.json").read_bytes()),
                "published projection",
            )
        print(
            result["status"],
            result["continuous_hits"],
            result["journals"]["P106"]["registered"]["decode4"],
        )
    except Exception as exc:
        if out:
            (out / "FAIL.json").write_text(json.dumps(dict(error=repr(exc))) + "\n")
        raise


if __name__ == "__main__":
    main()
