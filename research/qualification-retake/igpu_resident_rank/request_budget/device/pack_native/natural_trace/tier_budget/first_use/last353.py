"""Cross the sealed T1 victim offers with the packed arm's strict first demands."""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
ENTRY = HERE.parents[6] / "layer_major_entry"
P = run_path(str(HERE / "score.py"))
OLD = run_path(str(ENTRY / "screen.py"))
AUDIT = run_path(str(OLD["INT"] / "t1_capture/audit.py"))
check, checked = P["check"], P["checked"]
ENTRY_SHA = "e1c649c0c9dadd0ab4662af2c3f97d2775a167364073538fa6525922fab8770a"
FIRST_SHA = "cbbba4262589e1c55aa1f57393f207384dc42c3ddea7a2bd5c299ef5d79fa01e"


def ranks(rows, first_call):
    table = {}
    for row in rows:
        if row.kind == 27:
            key = row.call - first_call, row.tile, row.layer, row.b
            check(key not in table, "duplicate routed row")
            table[key] = tuple((row.a >> (8 * i)) & 255 for i in range(4))
    return table


def strict_keys(rows, host):
    rel = P["RELEASE"]
    initial, spans, reserves, first, demand, enqueues, service = rel["scopes"](rows, host)
    keys, prices = {}, defaultdict(list)
    for key, (gen, site) in demand.items():
        if key in initial or first.get(key) != gen or site[-1] not in (-1, 0):
            continue
        if enqueues[gen][:2] == (0, site) and reserves[gen][0] == site:
            keys[key] = site
            prices[site].append(rel["price"](service[gen], reserves[gen][1], spans[site][1]))
    check(prices == P["strict_sites"](rows, host), "identities and prices of every strict release")
    return keys


def score(part63, family):
    old = checked(ENTRY / "receipt.json", ENTRY_SHA)
    check(OLD["run"](part63) == old, "T1 seal, conservation, slots and original bank")
    arm = part63 / "tesy-policy-natural-physical-20261125-r02/ON"
    arm_receipt = checked(arm / "receipt.json", old["source_seals"]["arm"])
    cut = checked(arm / "before-t2.json", arm_receipt["before_t2_sha256"])
    candidates = checked(arm / "before-t2-candidates.json", cut["candidate_file_sha256"])
    read = P["TIER"]["PFJ"]["read_journal"]
    historical, header = read(arm / "raw/events.pfj")
    check(header["journal_sha256"] == old["source_seals"]["journal"], "part 63 journal")
    prefix, rest = historical[: cut["records"]], historical[cut["records"] :]
    check(AUDIT["record_digest"](prefix) == cut["sha256"], "causal T1 cut")
    slots, fifo, victims = AUDIT["state_before"](prefix)
    bank = set(map(tuple, candidates["capacities"]["353"]["ordered_keys"]))

    first = checked(HERE / "result.json", FIRST_SHA)
    rows, header = read(family / "ON/raw/events.pfj")
    journal_sha = header["journal_sha256"]
    check(journal_sha == first["input_sha256"]["ON/raw/events.pfj"], "qualified part 97 journal")
    host = P["TIER"]["NATIVE"]["host_trace"](rows)
    check(host["route"] == first["route"], "all ranked rows")
    initial = sorted((r.layer, r.slot, r.expert, r.gen, r.a, r.b) for r in rows if r.kind == 5)
    check(initial == [(i // 40, i % 40, *s) for i, s in enumerate(slots)], "per-slot identity")
    check(not fifo and not any(r.kind == 6 for r in rows), "empty initial queues")
    logical = {(layer, e) for layer, _, e, _, _, _ in initial}
    route = ranks(rows, 1)
    check(route == ranks(rest, rest[0].call), "ordered logical ranks at every call/tile/layer/row")
    tiles = defaultdict(set)
    for (call, tile, layer, _), experts in route.items():
        if call < 2:
            for e in experts:
                tiles[layer, e].add((call + 1, tile))
    missing = tiles.keys() - logical
    tier = OLD["tier"]
    check(tier(missing & bank) == old["useful_in_last353"], "original and packed intersection")
    strict = strict_keys(rows, host)
    cpu_layers = checked(HERE.parent / "evidence/packed.json", P["TIER_SHA"])["tier_layers"]["CPU"]
    cpu = {k for k in strict if k[0] in cpu_layers}
    earlier = {k for k in cpu if any(t < strict[k][:2] for t in tiles[k])}
    check(len(cpu) == first["by_tier"]["CPU"]["total"]["jobs"], "qualified CPU denominator")
    offers = set(victims)
    populations = {"prior_tile": earlier, "last353": cpu & bank, "all_offers": cpu & offers}
    return {
        "entry_receipt_sha256": ENTRY_SHA,
        "first_use_receipt_sha256": FIRST_SHA,
        "journal_sha256": {"63": old["source_seals"]["journal"], "97": journal_sha},
        "candidate_sha256": cut["candidate_file_sha256"],
        "prefix_sha256": cut["sha256"],
        "prefix_records": len(prefix),
        "t1_cut": {
            k: candidates[k]
            for k in (
                "first_position",
                "last_position",
                "t1_calls",
                "victim_offers",
                "distinct_victim_keys",
            )
        },
        "identical_slots": len(initial),
        "identical_routed_rows": len(route),
        "identical_prefill_routed_rows": sum(k[0] < 2 for k in route),
        "missing_at_entry": tier(missing),
        "last353_of_missing": tier(missing & bank),
        "strict": tier(strict),
        "last353_of_strict": tier(strict.keys() & bank),
        "cpu_keys_covered": {k: len(v) for k, v in populations.items()},
        "cpu_keys_still_to_advance": {
            rate: {
                k: max(0, len(cpu) - len(v) - cap["max_jobs_served_after_release"])
                for k, v in populations.items()
            }
            for rate, cap in first["volume"].items()
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("part63", "family", "new-output-dir"):
        parser.add_argument("--" + option, type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    with (args.new_output_dir / "receipt.json").open("x") as out:
        try:
            result = score(args.part63, args.family)
        except Exception as exc:
            json.dump({"status": "FAIL_PRESERVED", "reason": str(exc)}, out)
            raise
        json.dump(result, out, indent=2, sort_keys=True)
        out.write("\n")
