"""Charge only cold generations consumed by a routed prefill wave before RETURN(148)."""

import argparse
import collections
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
INT = HERE.parent
spec = importlib.util.spec_from_file_location("router_volume_deps", INT / "t1_set_floor/screen.py")
sf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sf)
src, need = sf.src, sf.need
replay = src.admit.t2
METHOD = "cbcdf0384579228de4061da9b87044356c46c8320504637be379fe97a2850363"
PAYLOAD = 3 * 4406400


def consumed(rows, meta):
    slots, reserved, why, comps, pub, delivered = {}, {}, {}, {}, {}, {}
    ranks, demands = {}, []
    current = None
    cut = False
    for r in rows:
        site = (r.call, r.tile, r.layer, r.wave)
        g = src.fd.identity(r)
        pos = r.layer, r.slot
        if r.kind == 5:
            need(r.a in (0, 2) and r.b == 0, "initial slot not drained")
            slots[pos] = (g, r.a)
        elif r.kind == 9:
            need(current is None, "nested remap")
            current, demands = site, []
        elif r.kind == 26:
            # PENDING_AT_RETURN cannot belong to a consumed slot at the final cut.
            continue
        elif r.kind == 27:
            rank = ranks.setdefault(site[:3], [])
            need(site == current and site[3] <= 0 and len(rank) == 4 * r.b, "rank row")
            rank.extend((r.a >> (8 * i)) & 255 for i in range(4))
        elif r.kind == 11:
            old, state = slots[pos]
            need(
                g not in reserved and old[2] + 1 == r.gen and old[3] == r.a and state in (0, 2),
                "reservation",
            )
            reserved[g] = site
            slots[pos] = (g, 1)
        elif r.kind == 12:
            if g not in why:
                need(g in reserved and r.a in (0, 2) and reserved[g] == site, "first enqueue")
                why[g] = r.a
            else:
                need(r.a == 1, "repeated ticket not promotion")
        elif r.kind == 10:
            need(
                site == current and slots[pos][0] == g and g not in demands,
                "stale/duplicate demand",
            )
            demands.append(g)
        elif r.kind == 13:
            need(g in why and g not in comps, "duplicate productive dispatch")
            comps[g] = []
        elif r.kind in (15, 16):
            comps[g].append(r)
        elif r.kind == 17:
            records = comps[g]
            need(
                g not in pub
                and slots[pos] == (g, 1)
                and [x.kind for x in records] == [15, 16] * 3
                and {x.component for x in records[::2]} == {0, 1, 2}
                and {x.worker for x in [*records, r]} == {r.worker}
                and all(x.ns <= y.begin for x, y in zip(records, records[1:], strict=False))
                and records[-1].ns <= r.ns,
                "publication after all serial components",
            )
            counts = [0, 0]
            for rd, st in zip(records[::2], records[1::2], strict=True):
                offset, size = meta[r.layer, rd.component]
                replay.planner.selected_range(
                    r.expert, offset, size, rd.a, rd.b, rd.c, replay.planner.MODEL_SIZE
                )
                need(
                    st.component == rd.component
                    and rd.error == st.error == 0
                    and st.a == size
                    and st.b == r.slot * size,
                    "SET byte coverage",
                )
                counts[0] += size
                counts[1] += rd.c
            pub[g] = tuple(counts)
            slots[pos] = (g, 2)
        elif r.kind == 20:
            need(site == current, "foreign barrier")
            ordered = list(dict.fromkeys(ranks[site[:3]]))
            actual = ordered if r.wave == -1 else ordered[18 * r.wave : 18 * (r.wave + 1)]
            need(
                len(actual) == len(demands) and set(actual) == {x[3] for x in demands},
                "authoritative ranks",
            )
            for key in demands:
                need(slots[key[:2]] == (key, 2), "consumer missing publication or stale slot")
                if key in reserved:
                    need(key in pub, "consumer before publication")
                    delivered.setdefault(key, site)
        elif r.kind == 23:
            need(
                current == site and all(slots[k[:2]] == (k, 2) for k in demands),
                "slot retired before remap end",
            )
            current = None
        elif r.kind == 2 and r.call == 2:
            need(
                current is None
                and not r.b
                and not r.c
                and all(st != 1 for _, st in slots.values()),
                "undrained 148",
            )
            cut = True
            break
    need(
        cut and set(why) == set(reserved) == set(comps) == set(pub),
        "all prefill generations complete",
    )
    return {g: (reserved[g], why[g], delivered.get(g), p, f) for g, (p, f) in pub.items()}


def subtotal(work, hits, budgets):
    parts = collections.defaultdict(collections.Counter)
    total = collections.Counter()
    for g, (origin, reason, use, payload, aligned) in work.items():
        phase = (
            f"call{origin[0]}_{'cpu' if g[0] < 25 else 'cuda'}_{'preload' if reason else 'demand'}"
        )
        line = collections.Counter(jobs=1, whole_fd=aligned if g not in hits else 0)
        if use is None:
            line["never_consumed"] += 1
        else:
            line["consumed"] += 1
            line["same_tile" if origin[:3] == use[:3] else "subsequent_tile"] += 1
            if g in hits:
                line["l2_hits"] += 1
            else:
                line.update(paid_jobs=1, payload=payload, aligned=aligned)
        parts[phase].update(line)
        total.update(line)
    prices = {}
    for n, limit in budgets.items():
        decision = (
            "NO_GO_VOLUME_PAYLOAD"
            if total["payload"] > limit
            else "NO_GO_FIXED_DIRECT_GEOMETRY"
            if total["aligned"] > limit
            else "HEADROOM_ONLY"
        )
        prices[n] = dict(
            decision=decision,
            budget_bytes=limit,
            excess_payload_bytes=total["payload"] - limit,
            excess_aligned_bytes=total["aligned"] - limit,
            minimum_payload_gbs=4.5 * total["payload"] / limit,
            minimum_aligned_gbs=4.5 * total["aligned"] / limit,
        )
    return dict(totals=total, by_origin=parts, denominators=prices)


def run(a):
    base = src.pinned(a.score_dir / "receipt.json", sf.SCORE)
    seal = src.pinned(a.prepared_dir / "receipt.json", sf.PREP)
    need(
        src.sha(HERE / "protocol.md") == METHOD
        and base["prepared_sha256"] == sf.PREP
        and seal["selection_sha256"] == src.sha(a.prepared_dir / "selection.json"),
        "frozen sources",
    )
    x = src.load_inputs(a.part, a.model, a.inventory, a.prepared_dir)
    need(x.journal == base["journal_sha256"], "same process")
    work = consumed(x.rows, x.meta)
    scored = base["results"]
    budgets = scored["current"]["budgets"]
    cold = subtotal(work, set(), budgets)
    need(
        len(work) == 1263
        and cold["totals"]["whole_fd"] == 16711176192
        and all(v[3] == PAYLOAD for v in work.values()),
        "R0 physical denominator",
    )
    arms = []
    for ctrl in scored["current"]["arms"]:
        keys = x.prefix["capacities"][str(ctrl["k"])]["ordered_keys"] if ctrl["warm"] else []
        arms.append(("recency" if ctrl["warm"] else "empty", ctrl, keys))
    for entry in scored["votes"]["arms"]["votes"]["by_t2_policy"].values():
        arms.append(("votes", entry["arm"], x.votes["banks"]["votes"]["ordered_keys"]))
    results = []
    for mode, ctrl, keys in arms:
        cache = replay.Policy(ctrl["family"], ctrl["k"], list(map(tuple, keys)))
        hist = replay.simulate(x.rows, cache)
        row = subtotal(work, cache.hits, budgets)
        need(
            hist["remaining_prefill_bytes"]
            == ctrl["remaining_prefill_bytes"]
            == row["totals"]["whole_fd"]
            and hist["prefill_hits"] == ctrl["prefill_hits"] == len(cache.hits & work.keys()),
            "finite arm",
        )
        results.append(dict(family=ctrl["family"], k=ctrl["k"], initial=mode, **row))
    return dict(
        status="PASS_ROUTER_WINDOW_CONSUMED_GENERATIONS",
        R0=cold,
        finite=results,
        source_journal_sha256=x.journal,
        archive_sha256=src.PART,
        local_sha256=sf.SCORE,
        prepare_sha256=sf.PREP,
        new_forwards=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("part", "model", "inventory", "prepared-dir", "score-dir", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a)
    except (KeyError, ValueError, TypeError, IndexError, OSError) as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    result.update(program_sha256=src.sha(Path(__file__)), protocol_sha256=METHOD)
    src.possible.save(a.new_output_dir / "receipt.json", result)
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
