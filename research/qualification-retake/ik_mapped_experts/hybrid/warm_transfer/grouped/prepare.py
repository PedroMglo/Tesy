"""Prepare a reduced-slot transfer cadence plan for the sealed first decode."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
RUNS = run_path(str(HERE.parent / "natural_runs/score.py"))
PAGES = RUNS["STEP"]["PAGES"]
IK = PAGES["IK"]
need, sha, SLAB = RUNS["need"], RUNS["sha"], RUNS["SLAB"]
RUN_RECEIPT = "d5a03811f9a92eae1745306a61ea71530b53b5688de35bae750c83d23d4521d4"
P97_PFJ = "05e32c2af753026e471fa61c9dcb43867ca6b9a3001045a2138bc96c422928dc"
ROLES = ("gate", "up", "down")


def install(mapping, inverse, layer, fills):
    need(list(fills) == sorted(fills), "noncanonical dispatch order")
    seen = set()
    for expert, slot in fills:
        key = layer, expert
        need(0 <= expert < 128 and 0 <= slot < 288, "expert or slot outside original geometry")
        need(key not in mapping and slot not in seen, "duplicate/mistaken fill")
        seen.add(slot)
        if slot in inverse:
            del mapping[inverse[slot]]
        inverse[slot] = key
        mapping[key] = slot


def group(layer, ids, before, after, fills, bases):
    need(len(ids) == len(set(ids)) == 4, "four independent router IDs")
    need(all(0 <= e < 128 for e in ids), "invalid router ID")
    need({e for e in ids if before[e] == -1} == {e for e, _ in fills}, "invalid misses")
    need(
        all(before[e] == after[e] for e in ids if before[e] >= 0)
        and all(after[e] == slot for e, slot in fills),
        "corrupted binding",
    )
    live = [after[e] for e in ids]
    need(all(0 <= s < 288 for s in live) and len(set(live)) == 4, "missing or aliased active slot")
    # The SET list stays the upstream list of runs even if compression creates an adjacency.
    need(RUNS["runs"](fills) == [1] * len(fills), "prior first decode contained a multi-fill run")
    translate = {slot: i for i, slot in enumerate(sorted(live))}
    reduced = [-1] * 128
    for e in ids:
        reduced[e] = translate[after[e]]
    ordered = []
    for role, base in zip(ROLES, bases, strict=True):
        for e, s in fills:
            ordered.append([role, e, s, translate[s], (base + e * SLAB) % 4096])
    return {
        "layer": layer,
        "ids_in_rank_order": ids,
        "ik_map_before": before,
        "ik_map_after": after,
        "ik_selected_slots": live,
        "selected_compact_slots": [reduced[e] for e in ids],
        "compact_map_to_send": reduced,
        "hits_to_seed_before_clock": [e for e in ids if before[e] >= 0],
        "weight_sets_role_expert_ik_slot_compact_slot_src_mod_page": ordered,
        "fills": len(fills),
    }


def make_plan(args):
    natural = args.runs / "receipt.json"
    need(sha(natural) == RUN_RECEIPT, "unsealed site census")
    prior = json.loads(natural.read_bytes())
    path = args.runs / "sites.jsonl"
    need(sha(path) == prior["sites_sha256"], "unsealed fill trajectory")
    need(sha(args.pfj) == P97_PFJ, "unsealed natural PFJ")
    raw, header = PAGES["NATIVE"]["PFJ"]["read_journal"](args.pfj)
    need(header["journal_sha256"] == P97_PFJ, "changed journal bytes")
    ranks = PAGES["PRED"]["L"]["ranks"](raw, 0)
    ids = {k[2]: list(v) for k, v in ranks.items() if k[0] == 3 and k[1] == 1 and k[3] == 0}
    need(sum(k[0] == 3 for k in ranks) == 36 and set(ids) == set(range(36)), "decode geometry")
    metadata = args.inventory.read_bytes()
    need(hashlib.sha256(metadata).hexdigest() == IK["INVENTORY"], "C283 metadata")
    need(tuple(IK["ROLES"]) == ROLES, "matrix order")
    bases = IK["layer_geometry"](metadata)
    table, inverse, groups = {}, {}, []
    with path.open() as file:
        for line in file:
            k, turn, call, tile, layer, fills, lengths = json.loads(line)
            if k != 288:
                continue
            if (turn, call) > (2, 3):
                break
            target = (turn, call, tile) == (2, 3, 1)
            if target:
                need(len(groups) == layer and len(inverse) == 288, "prefix/clock/order")
                before = [table.get((layer, e), -1) for e in range(128)]
            need(lengths == RUNS["runs"](fills), "run census")
            install(table, inverse, layer, fills)
            if target:
                after = [table.get((layer, e), -1) for e in range(128)]
                groups.append(group(layer, ids[layer], before, after, fills, bases[layer]))
    hist = Counter(r["fills"] for r in groups)
    fills = sum(n * count for n, count in hist.items())
    control = prior["phases"]["classlru_288"]["first_decode"]
    need(len(groups) == control["sites"] == 36 and fills == control["fills"] == 92, "sealed census")
    sets = sum(
        len(row["weight_sets_role_expert_ik_slot_compact_slot_src_mod_page"]) for row in groups
    )
    need(
        hist[0] == control["zero_fill_sites"] == 1 and sets == control["weight_set_calls"] == 276,
        "work",
    )
    private = args.new_output / "plan.json"
    with private.open("x") as out:
        json.dump(groups, out, separators=(",", ":"))
        out.write("\n")
    return dict(
        status="PREPARED_GROUP_CADENCE_ONLY",
        source_sha256=sha(Path(__file__)),
        protocol_sha256=sha(HERE / "protocol.md"),
        site_census_sha256=RUN_RECEIPT,
        fill_path_sha256=prior["sites_sha256"],
        pfj_sha256=P97_PFJ,
        inventory_sha256=IK["INVENTORY"],
        plan_sha256=sha(private),
        sites=len(groups),
        fill_histogram=dict(sorted(hist.items())),
        sites_with_no_fill=[r["layer"] for r in groups if r["fills"] == 0],
        role_major_weight_sets=sets,
        get_bytes=36 * 16,
        compact_map_bytes=36 * 128 * 4,
        weight_bytes=fills * 3 * SLAB,
        hits_to_seed_outside_clocks=4 * 36 - fills,
        future_triplet_intermediate_drains=fills,
        future_group_intermediate_drains=0,
        future_final_drains_per_mode=36,
        gpu_starts=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("pfj", "runs", "inventory", "new-output"):
        p.add_argument("--" + arg, type=Path, required=True)
    a = p.parse_args()
    a.new_output.mkdir(mode=0o700, exist_ok=False)
    try:
        r = make_plan(a)
    except Exception as e:
        r = {"status": "FAIL_PRESERVED", "error": str(e)}
    tmp = a.new_output / ".pending"
    with tmp.open("x") as out:
        json.dump(r, out, indent=2, sort_keys=True)
        out.write("\n")
    tmp.rename(a.new_output / "receipt.json")
    print(r["status"])
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
