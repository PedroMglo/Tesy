"""Bound compulsory prefill payloads for every order of the preserved routed tiles."""

import argparse
import hashlib
import json
import runpy
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
INT = HERE.parent / "phase_fd/integrated"
FRONT = INT / "t1_manager_bank/policy_snapshot/natural/prefill_frontier"
PAYLOAD = 13_219_200
SIZE = (263, 90)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(ok, name):
    if not ok:
        raise ValueError(name)


def tier(keys):
    cpu = sum(layer < 25 for layer, _ in keys)
    return {"cpu": cpu, "cuda": len(keys) - cpu, "total": len(keys)}


def sealed_json(path, digest):
    check(sha(path) == digest, path.name)
    return json.loads(path.read_bytes())


def run(part):
    oracle = sealed_json(
        FRONT / "oracle/evidence/receipt.json",
        "991fb5d4804b207e96e190101a0a0d68cad3a46cc1abb766fee47567fab39e9b",
    )
    seal = oracle["source_seals"]
    names = sealed_json(part / "manifest.json", seal["archive63"])["files"]
    root = part / "tesy-policy-natural-physical-20261125-r02/ON"
    arm = sealed_json(root / "receipt.json", seal["arm"])
    boundary = sealed_json(root / "before-t2.json", arm["before_t2_sha256"])
    candidates = sealed_json(root / "before-t2-candidates.json", arm["t1_candidates_sha256"])
    check(arm["t1_candidates_sha256"] == boundary["candidate_file_sha256"], "T1 input")
    source = INT / "t1_capture/audit.py"
    check(
        sha(source) == "8421320989e437594d4026d350269b07c3bb3c0c540a3d79f011a06534480089", "auditor"
    )
    audit = runpy.run_path(str(source))
    path = root / "raw/events.pfj"
    rows, h = audit["fd"].read_journal(path)
    check(
        h["journal_sha256"]
        == seal["journal"]
        == arm["journal_sha256"]
        == names[path.relative_to(part).as_posix()]["sha256"],
        "journal",
    )
    offset = boundary["records"]
    prefix, tail = rows[:offset], rows[offset:]
    check(audit["record_digest"](prefix) == boundary["sha256"], "causal prefix")
    check(json.loads(json.dumps(audit["capture_prefix"](prefix))) == candidates, "causal selection")
    slots, fifo, victims = audit["state_before"](prefix)
    check(not fifo and all(state == 2 and claim == 0 for _, _, state, claim in slots), "READY")
    primary = {(i // 40, entry[0]) for i, entry in enumerate(slots)}
    bank = set(map(tuple, candidates["capacities"]["353"]["ordered_keys"]))
    offers = set(victims)
    check(
        len(primary) == 1440 and bank <= offers and (tier(bank)["cpu"], tier(bank)["cuda"]) == SIZE,
        "input populations",
    )
    base = tail[0].call
    check(audit["conservation"](rows, h, None, base)["status"] == "PASS", "PFJ1 conservation")
    ranks, demands, position_rows, groups = (defaultdict(set) for _ in range(4))
    for r in tail:
        if r.call not in (base, base + 1):
            continue
        site = (r.call, r.tile, r.layer)
        if r.kind == 27:
            experts = [(r.a >> (8 * j)) & 255 for j in range(4)]
            check(len(set(experts)) == 4 and max(experts) < 128, "rank quartet")
            ranks[site].update(experts)
            position_rows[site].add(r.b)
        elif r.kind == 10:
            demands[site].add(r.expert)
            groups[(r.call, r.tile)].add((r.layer, r.wave))
    check(ranks == demands, "rank and demand unions for each tile-layer")
    tiles = sorted(groups)
    check([len(groups[x]) for x in tiles] == oracle["demand_groups_by_tile"], "six tile waves")
    width = [5, 32, 32, 32, 32, 20]
    for i, tile in enumerate(tiles):
        for layer in range(36):
            expected = (1 if i == 5 else 0) if layer == 35 else width[i]
            check(len(position_rows[tile + (layer,)]) == expected, "routed rows or pruning")
    entry = primary | bank
    by_call = [
        {(layer, e) for (c, _, layer), experts in ranks.items() if c == call for e in experts}
        for call in (base, base + 1)
    ]
    universe = by_call[0] | by_call[1]
    cold = universe - entry
    missing_without_bank = universe - primary
    possible = tier(missing_without_bank & offers)
    fixed_split = len(missing_without_bank) - sum(
        min(possible[k], cap) for k, cap in zip(("cpu", "cuda"), SIZE, strict=True)
    )
    pooled = len(missing_without_bank) - min(353, possible["total"])
    prices = sealed_json(
        FRONT / "transport/joint/receipt.json",
        "78a53e6d93fed1ad9a9236d74b60b234546d32041f5e572998240b243b82fb7e",
    )
    cross = {}
    for scope, terms in prices["conditional"].items():
        cross[scope] = {}
        for key, values in terms["pairs"].items():
            max_jobs = values["payload_budget_at_this_mean_rate_bytes"] // PAYLOAD
            need = max(0, len(cold) - max_jobs)
            cross[scope][key] = dict(
                max_jobs=max_jobs,
                extra_useful_needed=need,
                payload_bytes=need * PAYLOAD,
                equivalent_seconds_at_arm_mean=need * PAYLOAD / values["useful_bytes_per_s"],
                max_jobs_minus_fixed_split_floor=max_jobs - fixed_split,
            )
    return dict(
        status="TRACE_DERIVED_ENTRY_FRONTIER",
        source_seals=seal,
        protocol_sha256=sha(HERE / "protocol.md"),
        verifier_sha256=sha(Path(__file__)),
        distinct_demand=tier(universe),
        compulsory_call5=tier(by_call[0] - entry),
        new_call148=tier(by_call[1] - entry - by_call[0]),
        compulsory=tier(cold),
        missing_without_bank=tier(missing_without_bank),
        useful_in_last353=tier(missing_without_bank & bank),
        useful_in_observed_t1_victims=possible,
        absent_from_observed_primary_and_victims=tier(missing_without_bank - offers),
        total_distinct_t1_victims=tier(offers),
        best_fixed_split_min_jobs=fixed_split,
        best_pooled_min_jobs=pooled,
        conditional=cross,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--part63", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with args.output.open("x") as output:
        try:
            result = run(args.part63)
        except Exception as exc:
            json.dump({"status": "FAIL_PRESERVED", "error": str(exc)}, output)
            raise
        json.dump(result, output, sort_keys=True, indent=2)
        output.write("\n")
