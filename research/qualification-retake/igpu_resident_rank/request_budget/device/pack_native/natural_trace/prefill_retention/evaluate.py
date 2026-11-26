"""Price two prospective victim banks against the authenticated T2 first-use incidences."""

import argparse
import csv
import json
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
FULL = HERE.parents[1] / "full_prefix"
BANK = HERE.parent / "tier_budget/first_use/previous_layer/bank"
POLICY = run_path(str(HERE / "policy.py"))
PROFILE = run_path(str(FULL / "audit.py"))
B = run_path(str(BANK / "score.py"))
L = B["LAST"]
T = L["P"]["TIER"]
CHAIN = run_path(str(HERE.parent / "release/run.py"))
check, pinned, digest = (CHAIN[k] for k in ("check", "sealed", "digest"))
PROTOCOL = "910e831e1998fff1ee3192fe4fd90a6d8833fb225879145bbd559dd766bd595d"
POLICY_SHA = "e2ca80bf825b4d73b8f0ef85ef3a5fb3dd7393c5843089a57287f94f3322a785"
P97 = "e5012e559a2403145abc6f5317bddc8b83f95f1e09b592eb83a6baa2c18980a9"
P101 = "ba53f8bf1f863204ee95053e4f35ac50f048455b58071fbdfc024d8215f048ac"
SIZE, CAP = B["SIZE"], 353


def bindings(rows):
    slots = {}
    for r in rows:
        if r.kind == 5:
            key = r.layer, r.slot
            check(key not in slots, "duplicate initial slot")
            slots[key] = (r.expert, r.gen, r.a, r.b)
    check(set(slots) == {(i, s) for i in range(36) for s in range(40)}, "initial 1440 slots")
    return slots


def delta(left, right):
    keys = left.keys() & right.keys()
    return {
        "reference_only": len(left.keys() - right.keys()),
        "new_only": len(right.keys() - left.keys()),
        "different": sum(left[k] != right[k] for k in keys),
        "equal": sum(left[k] == right[k] for k in keys),
    }


def tier_counts(keys, tiers):
    n = Counter(tiers[k[0]] for k in keys)
    return {tier: n[tier] for tier in ("CPU", "CUDA0")}


def best_counts(groups, ticks, whole, capacity):
    """Each first-use key occurs once; decreasing marginal savings make this optimum exact."""
    choices = []
    for site, n, offered, gap in groups:
        check(0 <= offered <= n and gap >= 0, "site population")
        residual = [B["cost"](n - i, gap, ticks, whole) for i in range(offered + 1)]
        gains = [a - b for a, b in pairwise(residual)]
        check(gains == sorted(gains, reverse=True), "non-concave per-site gain")
        choices.extend((-g, i, site) for i, g in enumerate(gains) if g > 0)
    # Ties go to an earlier selection within a site before a later selection.
    return Counter(site for _, _, site in sorted(choices)[:capacity])


def project(strict, windows, selected, offered, budget, capacity=CAP):
    grouped = defaultdict(set)
    for key, site in strict.items():
        grouped[site].add(key)
    check(grouped.keys() == windows.keys(), "window/key domain")
    cells = [
        (site, len(pop), len(pop & offered), windows[site]) for site, pop in sorted(grouped.items())
    ]
    hits = {k: {s: len(pop & bank) for s, pop in grouped.items()} for k, bank in selected.items()}
    hits["empty"] = dict.fromkeys(windows, 0)
    results = {}
    for rate in (4_500_000_000, 8_000_000_000):
        ticks, rem = divmod(SIZE * 10**9, rate)
        check(rem == 0, "nonintegral expert time")
        for label, whole in (("partial", False), ("whole", True)):
            oracle = best_counts(cells, ticks, whole, capacity)
            estimates = {}
            for name, counts in (hits | {"retrospective": oracle}).items():
                floor = sum(
                    B["cost"](n - counts.get(s, 0), g, ticks, whole) for s, n, _, g in cells
                )
                h = sum(counts.values())
                estimates[name] = {
                    "served_keys": h,
                    "remaining_no_prediction_ns": (len(strict) - h) * ticks,
                    "conditional_floor_ns": floor,
                    "margin_ns": budget - floor,
                    "decision": "HEADROOM_ONLY" if floor <= budget else "NO_GO_FIXED_SCOPE",
                }
            estimates["retrospective"]["minimum_ideal_cpu_acquisition_bytes"] = (
                sum(oracle.values()) * SIZE
            )
            results[f"{rate}_{label}"] = estimates
    table = [
        {
            "site": site,
            "jobs": n,
            "offers": m,
            "gap_ns": g,
            **{name: hit[site] for name, hit in hits.items() if name != "empty"},
        }
        for site, n, m, g in cells
    ]
    return results, table


def read_new(root, outer_sha):
    outer = pinned(root / "family.json", outer_sha)
    check(
        outer["status"] == "PASS_C281_FULL_PREFIX_NATURAL_PAIR"
        and outer["identity"]["order"] == ["OFF", "ON"]
        and outer["identity"]["historical_family_sha256"] == P97
        and (outer["model_launches"], outer["requests"]) == (2, 4),
        "natural family pedigree",
    )
    arm = root / "ON"
    link = outer["arms"]["ON"]
    meta = pinned(arm / "arm.json", link["sha256"])
    check(meta == link["arm"] and meta["status"] == "PASS_ONE_NATURAL_ARM", "ON membership")
    receipt = pinned(arm / "receipt.json", meta["receipt_sha256"])
    audit = pinned(arm / "journal-audit.json", meta["journal_audit_sha256"])
    proof = receipt["full_prefix"]
    check(
        proof["label"] == "ON"
        and receipt["status"] == "PASS_TWO_NATURAL_REQUESTS_LOCAL_HISTORY"
        and receipt["transport"]["mode"] == "P"
        and meta["grade"]["status"] == "PASS_REVIEWED_TWO_NATURAL_TURNS"
        and meta["grade"]["receipt_sha256"] == meta["receipt_sha256"]
        and audit["status"] == meta["journal_status"] == "PASS_FULL_PREFIX_NATURAL_JOURNAL"
        and meta["journal_audit_sha256"] == proof["journal_audit_sha256"],
        "completed native P observation",
    )
    sealed = pinned(arm / "before-t2.json", meta["before_t2_sha256"])
    banks = pinned(arm / "before-t2-candidates.json", meta["t1_candidates_sha256"])
    check(
        meta["before_t2_sha256"] == proof["before_t2_sha256"]
        and meta["t1_candidates_sha256"]
        == sealed["candidate_file_sha256"]
        == proof["t1_candidates_sha256"]
        and sealed["policy_sha256"] == banks["policy_sha256"] == POLICY_SHA,
        "pre-POST evidence",
    )
    pfj = arm / "observer/events.pfj"
    check(digest(pfj) == proof["journal_sha256"], "whole closed journal")
    stat = receipt["transport"]["data_stat"]
    grade = PROFILE["audit_closed"](pfj, sealed, stat["pack"], stat["model"])
    check(json.loads(json.dumps(grade)) == audit, "reopened native service and cut")
    cut, total = PROFILE["metadata"](pfj, True)

    def t1():
        return PROFILE["iter_rows"](pfj, 0, cut)

    check(
        POLICY["seal"](t1(), sealed["prefill_calls"]) == banks
        and cut == proof["prefix_records"] == sealed["records"]
        and len(PROFILE["T1"]) == 86,
        "pre-POST bank or observation changed after close",
    )
    # Independent last-offer ordering, including all of T1, through the byte-sealed cut only.
    last = {}
    for r in t1():
        if r.kind == 11 and r.a >= 0:
            k = r.layer, r.a
            last.pop(k, None)
            last[k] = None
    check(
        list(last)[-CAP:] == [tuple(k) for k in banks["banks"]["lru"]["ordered_keys"]]
        and set(last) == {tuple(k) for k in banks["offered_keys"]},
        "complete last-offer bank or victim universe",
    )
    rows = [
        r._replace(call=r.call - 86) if r.call else r
        for r in PROFILE["iter_rows"](pfj, cut, total - cut)
    ]
    post1, post2 = proof["post_entry_ns"]
    first, final = next(t1()), next(PROFILE["iter_rows"](pfj, cut - 1, 1))
    check(
        proof["trigger_before_open_ns"]
        <= post1
        <= first.ns
        <= final.ns
        <= sealed["seal_start_ns"]
        <= sealed["selection_saved_ns"]
        <= proof["seal_end_ns"]
        <= post2
        <= rows[0].ns
        and post2 - sealed["seal_start_ns"] <= 15_000_000_000,
        "both selections precede native T2",
    )
    logname = receipt["native_ids"]["raw_stderr_file"]
    check(Path(logname).name == logname, "producer log name")
    log = arm / "raw" / logname
    check(digest(log) == receipt["native_ids"]["stderr_sha256"], "producer log")
    tiers, _ = T["mapping"](log.read_bytes(), rows)
    return (
        banks,
        rows,
        tiers,
        {
            "family_sha256": outer_sha,
            "journal_sha256": proof["journal_sha256"],
            "before_t2_sha256": meta["before_t2_sha256"],
            "selection_sha256": meta["t1_candidates_sha256"],
            "audit_sha256": meta["journal_audit_sha256"],
            "prefix_sha256": sealed["sha256"],
            "t1_positions": [sealed["first_position"], sealed["last_position"]],
            "t1_routed_rows": sealed["ranks"],
            "t1_prefill_calls": sealed["prefill_calls"],
            "t1_records": cut,
            "t2_records": total - cut,
        },
    )


def reference(part63, p97, part101):
    # This reopens the part-63 predecessor seal and checks every slot and ordered rank in P97.
    result = pinned(BANK.parents[1] / "last353.json", B["LAST_SHA"])
    check(L["score"](part63, p97) == result, "parts 63/97 correspondence and prior LRU")
    projection = part101 / "tesy-pack-previous-layer-bank-20261125-r01"
    base = pinned(projection / "receipt.json", P101)
    raw = projection / "windows.tsv"
    check(
        base["journals_sha256"] == result["journal_sha256"]
        and base["source_receipts_sha256"]["membership"] == B["LAST_SHA"]
        and digest(raw) == base["windows_sha256"]
        and base["budget_ns"] == 90_641_339,
        "archived window membership and timing",
    )
    fam, _, _, _ = CHAIN["chain"](p97, P97)
    rows, header = T["PFJ"]["read_journal"](p97 / "ON/raw/events.pfj")
    check(header["journal_sha256"] == result["journal_sha256"]["97"], "part 97")
    tier_authority = pinned(BANK.parents[2] / "evidence/packed.json", L["P"]["TIER_SHA"])
    tiers = {i: name for name, layers in tier_authority["tier_layers"].items() for i in layers}
    strict = L["strict_keys"](rows, T["NATIVE"]["host_trace"](rows))
    cpu = {k: v for k, v in strict.items() if tiers[k[0]] == "CPU"}
    with raw.open() as f:
        entries = [
            dict((k, int(v)) for k, v in row.items()) for row in csv.DictReader(f, delimiter="\t")
        ]
    sites = Counter(cpu.values())
    windows = {tuple(r[k] for k in ("call", "tile", "layer", "wave")): r["gap_ns"] for r in entries}
    check(
        len(entries) == len(windows) == 110
        and len(cpu) == 375
        and sites == {s: r["jobs"] for s, r in zip(windows, entries, strict=True)},
        "375 identified first demands and 110 horizons",
    )
    old = part63 / "tesy-policy-natural-physical-20261125-r02/ON/before-t2-candidates.json"
    sealed = pinned(old, result["candidate_sha256"])
    old_lru = set(map(tuple, sealed["capacities"]["353"]["ordered_keys"]))
    return (
        rows,
        cpu,
        tiers,
        windows,
        old_lru,
        base,
        fam["arms"]["ON"]["arm"]["grade"]["trajectories"],
    )


def read_current(rows, tiers):
    host = T["NATIVE"]["host_trace"](rows)
    strict = L["strict_keys"](rows, host)
    return host["route"], strict, {k: v for k, v in strict.items() if tiers[k[0]] == "CPU"}


def delivery(rows, bank, tiers):
    """Hold T1 bytes read-only throughout T2, replay the original primary reservations."""
    count = Counter()
    used = set()
    for row in rows:
        key = row.layer, row.expert
        if row.kind == 11 and key in bank:
            phase = "prefill" if row.call <= 2 else "decode"
            count[phase, tiers[row.layer]] += 1
            used.add(key)
    return {
        phase: {
            tier: {"reservations": count[phase, tier], "payload_bytes": count[phase, tier] * SIZE}
            for tier in ("CPU", "CUDA0")
        }
        for phase in ("prefill", "decode")
    }, tier_counts(used, tiers)


def evaluate(a):
    check(
        digest(HERE / "protocol.md") == PROTOCOL and digest(HERE / "policy.py") == POLICY_SHA,
        "prospective policy and protocol",
    )
    sealed, rows, tiers, source = read_new(a.session, a.session_sha256)
    route, strict, cpu = read_current(rows, tiers)
    ref, old_cpu, old_tiers, windows, old_lru, prices, old_trajectory = reference(
        a.part63, a.p97, a.part101
    )
    fam = pinned(a.session / "family.json", a.session_sha256)
    check(fam["arms"]["ON"]["arm"]["grade"]["trajectories"] == old_trajectory, "task and exact IDs")
    offered = set(map(tuple, sealed["offered_keys"]))
    selected = {k: set(map(tuple, v["ordered_keys"])) for k, v in sealed["banks"].items()}
    observation = {}
    for name, bank in selected.items():
        data = sealed["banks"][name]
        deliveries, used = delivery(rows, bank, tiers)
        observation[name] = {
            "t2_read_only_bank_same_reservations": deliveries,
            "admissions_without_a_t2_delivery": {
                tier: n - used[tier] for tier, n in data["copies"].items()
            },
            **{k: v for k, v in data.items() if k != "ordered_keys"},
            "held_by_tier": tier_counts(bank, tiers),
            "t1_acquisition_bytes": {k: n * SIZE for k, n in data["copies"].items()},
            "strict_prefill_t2_hits": tier_counts(bank & strict.keys(), tiers),
            "strict_prefill_t2_delivery_bytes": {
                k: n * SIZE for k, n in tier_counts(bank & strict.keys(), tiers).items()
            },
        }
    new_slots, ref_slots = bindings(rows), bindings(ref)
    comparisons = {
        "initial_expert_generation_state_claim": delta(ref_slots, new_slots),
        "ordered_top4": delta(L["ranks"](ref, 1), L["ranks"](rows, 1)),
        "strict_cpu_key_to_site": delta(old_cpu, cpu),
        "placement": delta(old_tiers, tiers),
    }
    check(
        all(r.kind != 6 for r in ref + rows)
        and all(v[-2:] == (2, 0) for v in [*ref_slots.values(), *new_slots.values()]),
        "both primary pools READY and unclaimed, no snapshot FIFO",
    )
    summary = {
        "status": "TRACE_DERIVED_FULL_PREFIX_BANKS",
        "method_sha256": digest(Path(__file__)),
        "protocol_sha256": PROTOCOL,
        "policy_sha256": POLICY_SHA,
        "new_source": source,
        "prior_sources": {
            "97_family": P97,
            "63_97_correspondence": B["LAST_SHA"],
            "101_windows": P101,
        },
        "route": route,
        "correspondence": comparisons,
        "banks": observation,
        "distinct_offered_t1": tier_counts(offered, tiers),
        "strict_prefill_t2_jobs": tier_counts(strict, tiers),
        "strict_prefill_t2_offered": tier_counts(strict.keys() & offered, tiers),
        "last353_and_prefill_intersection": tier_counts(
            selected["lru"] & selected["prefill"], tiers
        ),
        "old_suffix_last353_and_new_lru": tier_counts(old_lru & selected["lru"], tiers),
        "capacity": CAP,
        "record_payload_bytes": SIZE,
        "retrospective_maximum_cpu_coverage": min(CAP, len(cpu.keys() & offered)),
        "t1_copy_and_t2_restore_clock": "UNMEASURED",
    }
    mismatch = [
        label
        for label, counts in comparisons.items()
        if any(counts[k] for k in ("reference_only", "new_only", "different"))
    ]
    if mismatch:
        summary.update(status="INCONCLUSIVE_CLOCK_TRANSFER", mismatched=mismatch)
        return summary, []
    result, table = project(cpu, windows, selected, offered, prices["budget_ns"])
    for name, estimate in result.items():
        rate, granularity = name.split("_")
        previous = prices["cases"]["8" if rate == "8000000000" else "4p5"][granularity]
        check(
            estimate["empty"]["conditional_floor_ns"] == previous["ns"]["previous"],
            "historical empty-bank ablation",
        )
    return summary | {"budget_ns_at_p97_clocks": prices["budget_ns"], "cases": result}, table


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("session", "part63", "p97", "part101", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--session-sha256", required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        report, table = evaluate(a)
        if table:
            dest = a.new_output_dir / "windows.tsv"
            with dest.open("x") as f:
                columns = [
                    "call",
                    "tile",
                    "layer",
                    "wave",
                    "jobs",
                    "offers",
                    "gap_ns",
                    "lru",
                    "prefill",
                ]
                writer = csv.writer(f, delimiter="\t", lineterminator="\n")
                writer.writerow(columns)
                for row in table:
                    writer.writerow([*row["site"], *(row[k] for k in columns[4:])])
            report["windows_sha256"] = digest(dest)
    except Exception as exc:
        report = {"status": "FAIL_PRESERVED", "reason": f"{type(exc).__name__}: {exc}"}
    with (a.new_output_dir / "receipt.json").open("x") as out:
        json.dump(report, out, sort_keys=True, indent=2, allow_nan=False)
        out.write("\n")
    print(report["status"], report.get("reason", ""))
    return int(report["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
