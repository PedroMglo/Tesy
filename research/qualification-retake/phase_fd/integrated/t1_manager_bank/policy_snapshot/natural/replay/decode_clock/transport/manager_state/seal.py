"""Prepare and reload both drained manager states at T2's first single-position decode."""

import argparse
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
transport = run_path(HERE.parent / "prepare.py")
dc, prev = transport["dc"], transport["prev"]
need, sha, encode = transport["need"], transport["sha"], transport["encode"]
PLAN_SHA = "aed09397a16ed706365d73e0d2535427528476b41d66e3d5e43ad90da345d79a"


def export_cut(manager):
    pools = []
    for pool in manager.pools:
        need(not pool.possible_loading and pool.next_wave == pool.next_count, "pending wave at cut")
        pools.append(
            dict(
                clock=pool.clock,
                age=pool.ages.copy(),
                frequency=pool.heat.copy(),
                slots=[
                    [e, gen, 0 if e == -1 else 2, 0]
                    for e, gen in zip(pool.ids, pool.gen, strict=True)
                ],
            )
        )
    return dict(remap_calls=manager.calls, decay_interval=manager.interval, pools=pools)


def import_cut(cut, bank):
    pools = cut["pools"]
    need(
        len(pools) == 36
        and all(
            len(p["slots"]) == len(p["age"]) == 40 and len(p["frequency"]) == 128 for p in pools
        ),
        "cut dimensions",
    )
    need(type(cut["remap_calls"]) is int and cut["remap_calls"] >= 0, "global remap counter")
    return prev["Manager"](
        [s for p in pools for s in p["slots"]],
        [(p["clock"], *p["age"], *p["frequency"]) for p in pools],
        cut["remap_calls"],
        cut["decay_interval"],
        bank,
    )


def admissions_match(actual, planned, bank):
    expected = [
        (j["ordinal"], j["expert"], j["slot"], j["generation"], j["source"]) for j in planned
    ]
    values = [
        (i, e, s, gen, "bank" if e in bank else "disk")
        for i, (e, s, gen, _, reason) in enumerate(actual)
        if reason == 0
    ]
    need(len(values) == len(actual) and values == expected, "reservation or bank source")


def schedule(cut, selector, tail, plan, candidate):
    manager = import_cut(cut, selector)
    output = []
    count = Counter()
    for group, priced in zip(tail, plan["groups"], strict=True):
        ranks = group["ranks"]
        call, tile, layer, wave = group["site"]
        need(
            (call, tile, layer, wave) == tuple(priced[k] for k in ("call", "tile", "layer", "wave"))
            and tile == 1
            and wave == -1
            and len(ranks) == len(set(ranks)) == 4,
            "decode ranks",
        )
        pool = manager.pools[layer]
        before = list(zip(pool.ids, pool.gen, strict=True))
        reserved, demands = manager.callback(layer, wave, ranks)
        if candidate:
            admissions_match(reserved, priced["jobs"], selector[layer])
        else:
            need(reserved == group["new"] and demands == group["demands"], "observed demands/slots")
        need([e for e, _, _ in demands] == ranks, "rank order")
        jobs = []
        for e, slot, gen, victim, reason in reserved:
            need((victim, gen - 1) == before[slot] and reason == 0, "old generation or preload")
            source = "bank" if e in selector[layer] else "disk"
            jobs.append([e, slot, victim, gen - 1, gen, reason, source])
            count[source] += 1
        output.append(dict(ranks_to_slots=demands, reservations=jobs))
    need(manager.calls == cut["remap_calls"] + len(tail), "remap counter at end")
    return output, count, manager.emitted.hexdigest()


def seal(a):
    read = transport["full"]["read"]
    plan = read(a.plan, PLAN_SHA)
    replay = read(dc["REPLAY"] / "evidence/receipt.json", dc["REPLAY_SHA"])
    rows, slots, words, calls, interval, bank, bases, origin = prev["sources"](
        a.family, dc["FAMILY"]
    )
    need(all(origin[k] == replay[k] for k in origin), "source mismatch")
    index = read(a.index, transport["full"]["INDEX"])
    transport["metadata"](index, bases)
    need(
        plan["index_sha256"] == transport["full"]["INDEX"]
        and plan["family_sha256"] == dc["FAMILY"],
        "transport authorities",
    )
    groups, reads, counts = prev["segment"](rows)
    need(counts == replay["observed"], "physical manager conservation")
    start = groups[0]["site"][0] + 2
    tail = [g for g in groups if g["site"][0] >= start]
    need(len(tail) == 1656, "decode coverage")
    all_rows, journal = prev["fd"].read_journal(a.family / "ON/raw/events.pfj")
    need(journal["journal_sha256"] == origin["pfj_sha256"], "observed cut source")
    at = next(i for i, r in enumerate(all_rows) if r.kind == 1 and r.call == start)
    physical_slots, fifo, _ = prev["audit"]["state_before"](all_rows[:at])
    need(not fifo, "pending observed FIFO")
    del all_rows
    empty = [set() for _ in bank]
    cuts, arms, stats, slot_hashes = {}, {}, {}, {}
    for label, selector in (("r0", empty), ("carry", bank)):
        candidate = label == "carry"
        manager, result = prev["trajectory"](
            groups,
            reads,
            slots,
            words,
            calls,
            interval,
            bank,
            bases,
            priority=candidate,
            restore=False,
            reference=None,
        )
        need(result == {k: v for k, v in replay[label].items() if k != "comparison"}, "trajectory")
        cuts[label] = state = export_cut(manager)
        if not candidate:
            need(
                [tuple(s) for p in state["pools"] for s in p["slots"]] == physical_slots,
                "observed first decode state",
            )
        arms[label], stats[label], slot_hashes[label] = schedule(
            json.loads(encode(state)), selector, tail, plan, candidate
        )
        prefix = prev["Manager"](slots, words, calls, interval, selector)
        ranks = None
        for group in groups[: -len(tail)]:
            _, _, layer, wave = group["site"]
            if wave in (-1, 0):
                ranks = group["ranks"]
            prefix.callback(layer, wave, ranks)
        need(export_cut(prefix) == state, "regenerated entry")
        for row in arms[label]:
            prefix.emitted.update(bytes(slot + 1 for _, slot, _ in row["ranks_to_slots"]))
        need(
            prefix.emitted.hexdigest() == replay[label]["inferred_slot_stream_sha256"],
            "complete slot-by-rank stream after serialized cut",
        )
    need(
        stats == {"r0": {"disk": 1091}, "carry": {"disk": 797, "bank": 399}},
        "scheduled populations",
    )
    bank_keys = [[layer, e] for layer, members in enumerate(bank) for e in sorted(members)]
    need(len(bank_keys) == 353, "bank membership")
    # The sealed C290 index supplies the three matrix digests for each selected address.
    keys = {(layer, e) for layer, e in bank_keys}
    for cut in cuts.values():
        keys.update(
            (layer, e) for layer, p in enumerate(cut["pools"]) for e, *_ in p["slots"] if e >= 0
        )
    weights = []
    for layer, e in sorted(keys):
        entry = index["experts"][128 * layer + e]
        need(
            (entry["layer"], entry["expert"]) == (layer, e)
            and entry["pack_offset"] == (128 * layer + e) * transport["full"]["STRIDE"],
            "weight index",
        )
        weights.append(
            [
                layer,
                e,
                entry["pack_offset"],
                [c["sha256"] for c in transport["components"](entry, bases[layer])],
            ]
        )
    blob = dict(
        schema="tesy-single-position-manager-fixture-v1",
        family_sha256=dc["FAMILY"],
        transport_sha256=PLAN_SHA,
        index_sha256=plan["index_sha256"],
        entry=cuts,
        decode=arms,
        bank_layer_expert=bank_keys,
        initial_weight_windows=weights,
        sites_fields=["call", "tile", "layer", "wave"],
        sites=[g["site"] for g in tail],
        slot_fields=["expert", "generation", "state", "worker_claim"],
        demand_fields=["expert", "slot", "generation"],
        reservation_fields=[
            "expert",
            "slot",
            "victim",
            "previous_generation",
            "generation",
            "reason",
            "source",
        ],
        first_position=2197,
        last_position=2242,
    )
    raw = encode(blob) + b"\n"
    need(len(raw) < 8 << 20, "output budget")
    path = a.new_output_dir / "states.json"
    with path.open("xb") as f:
        f.write(raw)
    return dict(
        status="REPRODUCED_BOTH_DECODE_ENTRIES",
        state_sha256=sha(path),
        state_bytes=len(raw),
        source_family=dc["FAMILY"],
        transport_sha256=PLAN_SHA,
        index_sha256=plan["index_sha256"],
        origin_journal_sha256=origin["pfj_sha256"],
        index_windows=len(keys),
        groups=len(tail),
        active_ranks=4 * len(tail),
        bank_keys=len(bank_keys),
        admissions=stats,
        decode_rank_to_slot_sha256=slot_hashes,
        different_demand_groups=sum(
            r["ranks_to_slots"] != c["ranks_to_slots"]
            for r, c in zip(arms["r0"], arms["carry"], strict=True)
        ),
        different_entry_bindings=sum(
            a[:2] != b[:2]
            for x, y in zip(cuts["r0"]["pools"], cuts["carry"]["pools"], strict=True)
            for a, b in zip(x["slots"], y["slots"], strict=True)
        ),
        program_sha256=sha(Path(__file__)),
        protocol_sha256=sha(HERE / "protocol.md"),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("family", "index", "plan", "new-output-dir"):
        parser.add_argument("--" + k, type=Path, required=True)
    a = parser.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        git = [
            "git",
            "--no-optional-locks",
            "-c",
            "core.preloadIndex=false",
            "-c",
            "index.threads=1",
            "-C",
            str(HERE),
        ]
        need(not subprocess.check_output([*git, "status", "--porcelain"]), "dirty snapshot")
        report = seal(a)
        report["commit"] = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
        report["tree"] = subprocess.check_output(
            [*git, "rev-parse", "HEAD^{tree}"], text=True
        ).strip()
    except Exception as exc:
        report = dict(status="FAIL_PRESERVED", error=f"{type(exc).__name__}: {exc}")
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    print(report["status"], report.get("error", ""))
    return int(report["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
