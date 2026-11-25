"""Secondary intersection of strict first-use reservations and CPU remaps in the observed P."""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
TIER = run_path(str(HERE.parent / "score.py"))
RELEASE = run_path(str(HERE.parents[1] / "release/review.py"))
check, checked = TIER["check"], TIER["checked"]
NS, PAYLOAD = RELEASE["NS"], RELEASE["PAYLOAD"]
TIER_SHA = "44a00a0660c4430156ad0e705abee364c4c6cbeb608f4da08dc14c15a35c9277"
RELEASE_SHA = "32df78803853247dfc2f70878b4e0a71e64798680a3943c09e0515e679332650"
METHOD = "e77c26814735ce29b4318611d76be804a5c5fe25155f7923b36528d860ca3c77"


def required(budget, floor):
    return {
        "floor_ns": floor,
        "additional_ns": max(0, floor - budget),
        "decision": "NO_GO_FIXED_SCENARIO" if floor > budget else "HEADROOM_ONLY",
    }


def charges(population, budget):
    n = population["jobs"]
    useful = population["payload_bytes"]
    check(budget > 0 and n > 0 and useful == n * PAYLOAD, "identical useful byte denominator")
    prices = {}
    for bps in (8_000_000_000, 4_500_000_000):
        # Integer budget admits at most this many complete 3-matrix payloads at the given rate.
        fit = min(n, budget * bps // (NS * PAYLOAD))
        prices[str(bps)] = required(budget, useful * NS // bps) | {
            "max_jobs_served_after_release": fit,
            "min_jobs_avoided_or_served_earlier": n - fit,
            "min_bytes_off_the_link_or_outside_these_sites": max(0, useful - budget * bps // NS),
        }
    observed = population["read_floor_ns"]
    return {
        "volume": prices,
        "read_only": {"1x": required(budget, observed), "0.5x": required(budget, observed // 2)},
        "required_Bps_for_all_payloads": (useful * NS + budget - 1) // budget,
        "max_uniform_READ_cost_fraction": budget / observed,
    }


def strict_sites(rows, host):
    initial, spans, reserves, first_reserve, first_demand, enqueues, services = RELEASE["scopes"](
        rows, host
    )
    groups = defaultdict(list)
    for key, (generation, site) in first_demand.items():
        if key in initial or first_reserve.get(key) != generation or site[-1] not in (-1, 0):
            continue
        reason, queued_at, enqueued_ns = enqueues[generation]
        reserved_at, reserved_ns = reserves[generation]
        if reason != 0 or reserved_at != site or queued_at != site:
            continue
        start, finish = spans[site]
        check(
            start <= reserved_ns <= enqueued_ns <= services[generation][0].ns,
            "release precedes dispatch and is within its own callback",
        )
        groups[site].append(RELEASE["price"](services[generation], reserved_ns, finish))
    return groups


def assess(a):
    check(TIER["sha"](HERE / "protocol.md") == METHOD, "secondary analysis definition")
    parent = checked(HERE.parent / "evidence/packed.json", TIER_SHA)
    released = checked(HERE.parents[1] / "release/evidence.json", RELEASE_SHA)
    args = SimpleNamespace(
        arm="P",
        family=a.family,
        backend=a.backend,
        family_sha256=parent["family_sha256"],
        result_sha256=parent["http_sha256"]["T2-result.json"],
        http_sha256=parent["http_sha256"]["T2-request.jsonl"],
    )
    check(TIER["assess"](args) == parent, "full natural conservation and tier price")
    check(
        parent["family_sha256"] == released["inputs_sha256"]["family.json"]
        and parent["journal_sha256"] == released["inputs_sha256"]["ON/raw/events.pfj"],
        "same P family",
    )
    rows, _ = TIER["PFJ"]["read_journal"](a.family / "ON/raw/events.pfj")
    host = TIER["NATIVE"]["host_trace"](rows)
    groups = strict_sites(rows, host)
    summary = RELEASE["summary"](groups)
    check(
        summary == released["first_wave"] and summary["total"]["jobs"] == 567,
        "every frozen first-wave price including call, count, bytes and lanes",
    )
    tiers = {}
    for tier, layers in parent["tier_layers"].items():
        tiers[tier] = RELEASE["summary"]({s: v for s, v in groups.items() if s[2] in layers})
    for k, price in summary["total"].items():
        check(sum(t["total"][k] for t in tiers.values()) == price, "tier conservation: " + k)
    sc = parent["scenarios"]["CPU"]
    budget = 10 * NS - sc["remaining_floor_ns"]["first"]
    out = charges(tiers["CPU"]["total"], budget)
    return {
        "status": "TRACE_DERIVED_SECONDARY_FIXED_RELEASE",
        "scope": "P_STRICT_FIRST_USE_IN_CPU_PREFILL",
        "method_sha256": METHOD,
        "tier_receipt_sha256": TIER_SHA,
        "release_summary_sha256": RELEASE_SHA,
        "input_sha256": released["inputs_sha256"],
        "route": parent["route"],
        "sampled_ids_sha256": parent["sampled_ids_sha256"],
        "by_tier": tiers,
        "CPU_first_final_budget_ns": budget,
        "first_final_floor_if_all_CPU_remaps_free_ns": sc["remaining_floor_ns"]["first"],
        **out,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for option in ("family", "backend", "new-output-dir"):
        p.add_argument("--" + option, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        r = assess(a)
    except Exception as exc:
        r = {"status": "FAIL_PRESERVED", "reason": f"{type(exc).__name__}: {exc}"}
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(r, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(r["status"], r.get("reason", ""))
    return int(r["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
