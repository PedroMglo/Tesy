"""Limit the warm-state oracle to identities available in the sealed T1 suffix."""

import argparse
import hashlib
import importlib.util
import json
from array import array
from pathlib import Path

HERE = Path(__file__).resolve().parent
INT = HERE.parent
METHOD = "59685773deb771eeba257d688f4214f1c2864547fa69079417d5cb9ae90d6c19"
AUDITOR = "8421320989e437594d4026d350269b07c3bb3c0c540a3d79f011a06534480089"
JOBS = "bcb6688cc32aed075fd50bf3f92e9b8ca7038c193cb56e8afbdadb3a0dcd6a5f"
COLD = "1edac104fb4a96482cabd1ad35deb357e49a1823bc8a814f26149affd5aa7aa9"
JOINT = "5eea9fd586bb4c56d63964ed75184f73d06b44d2d5ee9d6e428cbc014ff76ce2"


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


source = module(INT / "t1_capture/audit.py", "opportunity_t1_source")
warm = module(INT / "warm_oracle/screen.py", "opportunity_price")
sha, pinned, check, floor = warm.sha, warm.read, warm.need, warm.lower_bound


def save(path, value):
    with path.open("x") as f:
        json.dump(value, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


def opportunities(rows):
    prefix = source.capture_prefix(rows)
    _, _, offers = source.state_before(rows)
    expelled = set(offers)
    available = expelled | {
        (r.layer, r.expert) for r in rows if r.kind == 17 or (r.kind == 5 and r.a == 2)
    }
    check(len(expelled) == prefix["distinct_victim_keys"], "T1 READY victims")
    return prefix, {"evicted_ready": sorted(expelled), "all_available": sorted(available)}


def seal(args):
    receipt = pinned(args.capture_dir / "receipt.json", args.capture_sha256)
    check(
        receipt["status"] == "PASS_T1_VICTIM_WINDOW_AND_T2_REFERENCE"
        and receipt["model_launches"] == 1
        and receipt["audit_program_sha256"] == AUDITOR
        and receipt["warm_oracle_sha256"] == JOINT,
        "terminal capture and auditor",
    )
    pre = pinned(args.capture_dir / "before-t2.json", receipt["before_t2_sha256"])
    check(0 < pre["records"] < 262144 and pre["bytes"] == 96 * pre["records"], "prefix length")
    with (args.capture_dir / "raw/events.pfj").open("rb") as f:
        f.seek(source.fd.HEADER.size)
        data = f.read(pre["bytes"])
    check(
        len(data) == pre["bytes"] and hashlib.sha256(data).hexdigest() == pre["sha256"],
        "sealed T1 bytes",
    )
    rows = [source.fd.Row(*x) for x in source.fd.RECORD.iter_unpack(data)]
    summary, pools = opportunities(rows)
    old = pinned(args.capture_dir / "before-t2-candidates.json", pre["candidate_file_sha256"])
    check(
        summary == old and receipt["t1_candidates_sha256"] == pre["candidate_file_sha256"],
        "pre-POST selection",
    )
    # Only authenticate the T2 audit after the independent T1 membership sets exist.
    audit = pinned(args.capture_dir / "boundary-audit.json", receipt["boundary_audit_sha256"])
    structure = audit["structure"]
    check(
        audit["status"] == "PASS"
        and audit["prefix"] == summary
        and structure["census_fd_checked"]
        and structure["t2_calls"] == 48
        and structure["first_decode_checked"]
        and structure["projections"]["host"]["equal"]
        and structure["projections"]["dispatch"]["equal"]
        and structure["journal_sha256"] == receipt["journal_sha256"]
        and structure["prior_journal_sha256"] == source.PRIOR,
        "T2 transport authority",
    )
    private = args.new_output_dir / "available.json"
    save(private, pools)
    return dict(
        status="PASS_T1_ONLY_AVAILABLE_IDENTITIES",
        capture_sha256=args.capture_sha256,
        audit_sha256=receipt["boundary_audit_sha256"],
        prefix_sha256=pre["sha256"],
        prefix_records=len(rows),
        prior_journal_sha256=structure["prior_journal_sha256"],
        before_t2_sha256=receipt["before_t2_sha256"],
        availability_sha256=sha(private),
        populations={label: source.per_tier(keys) for label, keys in pools.items()},
    )


def frontier(groups, allowed):
    """Within a group the q longest removable chains minimise max(maximum,work/4)."""
    seen, order, predecessors, dp = set(), [], [], [0]
    for group in groups:
        check(0 < len(group) <= 40, "invalid wave")
        removable, fixed = [], []
        for key, ns in group:
            check(key not in seen and type(ns) is int and ns > 0, "duplicate or invalid service")
            seen.add(key)
            if key in allowed:
                removable.append((key, ns))
            else:
                fixed.append(ns)
        removable.sort(key=lambda item: (-item[1], item[0]))
        order.append([k for k, _ in removable])
        costs = [floor(fixed + [ns for _, ns in removable[q:]]) for q in range(len(removable) + 1)]
        values, prev = [], array("B")
        for k in range(len(dp) + len(removable)):
            best, q = min(
                (dp[k - q] + costs[q], q)
                for q in range(max(0, k + 1 - len(dp)), min(k, len(removable)) + 1)
            )
            values.append(best)
            prev.append(q)
        dp = values
        predecessors.append(prev)

    def selected(k):
        chosen = set()
        for keys, prev in zip(reversed(order), reversed(predecessors), strict=True):
            q = prev[k]
            chosen.update(keys[:q])
            k -= q
        check(k == 0, "backtrack")
        return chosen

    return dp, selected


def price(groups, allowed, volume, fixed, budgets, caps):
    curve, selected = frontier(groups, allowed)
    output = []
    for cap in caps:
        k = min(cap, len(curve) - 1)
        chosen = selected(k)
        # If no more temporal chains can be removed, use any remaining space for
        # useful prefill identities first. The unbounded row includes the full set.
        spare = sorted(allowed - chosen, key=lambda key: (key not in volume, key))
        chosen.update(spare[: max(0, cap - k)])
        check(chosen <= allowed and len(chosen) == min(cap, len(allowed)), "invalid selection")
        cost = sum(floor([ns for key, ns in group if key not in chosen]) for group in groups)
        check(cost == curve[k], "witness cost")
        payload = warm.PAYLOAD
        volume_floor = len(volume - chosen) * payload
        best_volume = (len(volume) - min(cap, len(allowed & volume))) * payload
        scales = {}
        for a, b in ((1, 1), (4, 5)):
            wall = fixed + a * cost // b
            classes = {}
            for label, maximum in budgets.items():
                if wall > 10**10 or best_volume > maximum:
                    decision = "NO_GO_IN_THIS_OPPORTUNITY"
                elif volume_floor <= maximum:
                    decision = "HEADROOM_ONLY_CAUSAL_POLICY_REQUIRED"
                else:
                    decision = "INCONCLUSIVE_VOLUME_TRADEOFF"
                classes[label] = decision
            scales[f"{a}/{b}"] = {"first_floor_ns": wall, "decisions": classes}
        output.append(
            dict(
                capacity=cap,
                selected=len(chosen),
                selected_payload_bytes=len(chosen) * payload,
                selected_by_tier=source.per_tier(chosen),
                selected_sha256=source.digest(sorted(chosen)),
                selected_time_jobs=k,
                selected_prefill_volume_keys=len(chosen & volume),
                remaining_service_floor_ns=cost,
                prefill_volume_floor_bytes=volume_floor,
                best_possible_volume_bytes=best_volume,
                scales=scales,
            )
        )
    return output


def score(args):
    cold = pinned(INT / "t2_victims/receipt.json", COLD)
    seal_receipt = pinned(args.sealed_dir / "receipt.json", args.sealed_sha256)
    check(
        seal_receipt["status"] == "PASS_T1_ONLY_AVAILABLE_IDENTITIES"
        and seal_receipt["program_sha256"] == sha(Path(__file__))
        and seal_receipt["protocol_sha256"] == METHOD,
        "opportunity seal",
    )
    populations = pinned(args.sealed_dir / "available.json", seal_receipt["availability_sha256"])
    check(set(populations) == {"evicted_ready", "all_available"}, "opportunity policies")
    allowed = {}
    for name, rows in populations.items():
        keys = set(map(tuple, rows))
        check(
            sorted(keys) == [tuple(pair) for pair in rows]
            and all(len(key) == 2 and 0 <= key[0] < 36 and 0 <= key[1] < 128 for key in keys)
            and source.per_tier(keys) == seal_receipt["populations"][name],
            "sealed population",
        )
        allowed[name] = keys
    check(allowed["evicted_ready"] <= allowed["all_available"], "opportunity subset")
    pins = cold["sources"]
    plan_meta = pinned(args.plan_dir / "receipt.json", pins["plan"])
    plan = pinned(args.plan_dir / "plan.json", pins["plan_data"])
    on = pinned(args.prior_on_dir / "receipt.json", pins["on"])
    check(
        on["status"] == "PASS_C281_PFJ_ON"
        and plan_meta["status"] == "PASS_AUTHENTICATED_FIRST_READ_PLAN"
        and plan_meta["plan_sha256"] == pins["plan_data"],
        "historical process and plan",
    )
    rows, h = source.fd.read_journal(args.prior_on_dir / "raw/events.pfj")
    check(
        h["journal_sha256"]
        == pins["journal"]
        == seal_receipt["prior_journal_sha256"]
        == source.PRIOR,
        "historical PFJ",
    )
    orig = pinned(args.prior_on_dir / "journal-audit.json", pins["audit"])
    check(
        orig["status"] == "PASS"
        and orig["fd_identity_checked"]
        and orig["journal_sha256"] == h["journal_sha256"],
        "historical conservation",
    )
    groups = warm.jobs(plan, rows)
    check(
        len(groups) == 441
        and sum(map(len, groups)) == cold["mandatory_jobs"] == 875
        and sum(floor([ns for _, ns in g]) for g in groups)
        == cold["service_floor_ns"]
        == plan["original_service_floor_ns"]
        and cold["fixed_ns"] == plan["fixed_outside_callbacks_ns"],
        "compulsory service conservation",
    )
    primary = {(r.layer, r.expert) for r in rows if r.kind == 5 and r.a}
    demand = {(r.layer, r.expert) for r in rows if r.kind == 10 and r.call in (1, 2)}
    volume = demand - primary
    check(
        len(volume) == cold["distinct_absent"] == 852
        and len(volume) * warm.PAYLOAD == cold["payload_floor"],
        "compulsory victim prefill volume",
    )
    host = pinned(INT / "host_cache/evidence/receipt.json", pins["host_cache"])
    budgets = {label: v["allowed_bytes"] for label, v in host["gates"].items()}
    cases = {}
    for name, keys in allowed.items():
        cases[name] = {
            "population": len(keys),
            "eligible_volume_keys": len(volume & keys),
            "rows": price(
                groups, keys, volume, cold["fixed_ns"], budgets, [0, 239, 353, len(keys)]
            ),
        }
    return dict(
        status="PASS_OFFLINE_OPPORTUNITY_SCREEN",
        opportunities=cases,
        captured_state_sha256=seal_receipt["capture_sha256"],
        sealed_sha256=args.sealed_sha256,
        historical_raw_sha256=pins["journal"],
        plan_data_sha256=pins["plan_data"],
        cold_receipt_sha256=COLD,
        model_forwards=0,
        group_count=441,
        time_jobs=875,
        compulsory_prefill_keys=len(volume),
        allowed_volume_bytes=budgets,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(required=True, dest="phase")
    s, e = modes.add_parser("seal"), modes.add_parser("score")
    for p, names in (
        (s, ("capture-dir", "new-output-dir")),
        (e, ("sealed-dir", "plan-dir", "prior-on-dir", "new-output-dir")),
    ):
        for name in names:
            p.add_argument("--" + name, type=Path, required=True)
    s.add_argument("--capture-sha256", required=True)
    e.add_argument("--sealed-sha256", required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        check(
            sha(HERE / "protocol.md") == METHOD
            and sha(INT / "warm_oracle/screen.py") == JOBS
            and sha(INT / "t1_capture/audit.py") == AUDITOR
            and sha(source.SOURCE) == source.PIN
            and sha(INT / "mandatory.py") == warm.MANDATORY,
            "source identities",
        )
        result = (seal if args.phase == "seal" else score)(args)
    except (ValueError, KeyError, IndexError, TypeError, OSError) as exc:
        result = dict(status="FAIL_PRESERVED", error=f"{type(exc).__name__}: {exc}")
    result.update(protocol_sha256=METHOD, program_sha256=sha(Path(__file__)))
    save(args.new_output_dir / "receipt.json", result)
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
