"""Lower bounds on primary acquisitions per B3, on the exact AR observation cuts."""

import argparse
import hashlib
import json
import math
import struct
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
LOOKUP = run_path(str(HERE.parent / "screen.py"))
NATURAL, REOPEN, check = (LOOKUP[k] for k in ("NATURAL", "REOPEN", "check"))
PAYLOAD, WINDOW = (REOPEN["RELEASE"][k] for k in ("PAYLOAD", "WINDOW"))
FIELDS = ("end_carry", "known_demand", "restore_extra", "joint")


def tier(layer):
    return "cpu" if layer < 25 else "cuda"


def counts(keys):
    return {name: sum(tier(layer) == name for layer, _ in keys) for name in ("cpu", "cuda")}


def measure_sets(start, final, known):
    needed = known - start
    restore = final - start - known
    return {
        "end_carry": counts(final - start),
        "known_demand": counts(needed),
        "restore_extra": counts(restore),
        "joint": counts(needed | restore),
    }


def blocks(actions):
    check(actions[:2] == ["prefill", "prefill"], "prefill actions")
    groups = []
    for call, action in enumerate(actions[2:], 3):
        if action == "skip":
            check(groups and groups[-1][0] == "anchor", "skip without proposal")
            groups[-1][1].append(call)
        else:
            check(action in ("anchor", "ar"), "unknown action")
            groups.append((action, [call]))
    sizes = Counter(len(calls) for tag, calls in groups if tag == "anchor")
    check(sizes == {1: 5, 3: 6} and len(groups) == 34, "frozen acceptance cases")
    return groups


def footprint(slots):
    h = hashlib.sha256()
    resident = set()
    for (layer, place), (expert, gen, state) in sorted(slots.items()):
        h.update(struct.pack("<5q", layer, place, expert, gen, state))
        if state in (1, 2):
            resident.add((layer, expert))
    return h.hexdigest(), resident, any(s[2] == 1 for s in slots.values())


def census(events, handoff, num_calls):
    slots = {}
    for e in events:
        if e.kind == 5:
            loc = (e.layer, e.slot)
            check(loc not in slots, "duplicate initial slot")
            slots[loc] = e.expert, e.gen, e.a
    check(len(slots) == 1440, "initial primary")
    before, after, pending, crossed, ranks, reads = (
        {},
        {},
        set(),
        set(),
        defaultdict(list),
        defaultdict(Counter),
    )
    active = 0
    for e in events:
        if e.kind == 1:
            check(not active and e.call == len(before) + 1, "call order")
            active = e.call
            before[active] = footprint(slots)
        elif e.kind == 2:
            check(active == e.call and e.a == 0, "external return")
            after[active] = footprint(slots)
            if e.b or e.c or before[active][2] or after[active][2]:
                pending.add(active)
            active = 0
        elif e.kind == 11:
            loc = (e.layer, e.slot)
            old_e, old_g, old_s = slots[loc]
            check(old_e == e.a and old_s != 1 and old_g + 1 == e.gen, "reserve generation")
            slots[loc] = e.expert, e.gen, 1
        elif e.kind == 17:
            loc = (e.layer, e.slot)
            check(slots[loc] == (e.expert, e.gen, 1), "stale publication")
            slots[loc] = e.expert, e.gen, 2
        elif e.kind == 27 and e.call > 2:
            check(active == e.call and e.a in range(2**32), "rank scope")
            ids = e.a.to_bytes(4, "little")
            check(len(set(ids)) == 4 and max(ids) < 128, "expert range")
            ranks[e.call].extend((e.layer, expert) for expert in ids)
        elif e.kind == 30:
            b = reads[(e.call, tier(e.layer))]
            b.update(jobs=1, payload_bytes=PAYLOAD, requested_bytes=e.b, returned_bytes=e.c)
        if e.kind in (11, 12, 13, 16, 17, 30) and active != e.call:
            crossed.add(e.call)
    check(not active and len(after) == len(before) == num_calls, "call/return count")
    check(before[3][0] == handoff, "first decode primary identity")
    for c in range(3, num_calls + 1):
        check(len(set(ranks[c])) == len(ranks[c]) == 36 * 4, "one full top-k per layer in decode")
    for c in range(1, num_calls):
        if after[c][0] != before[c + 1][0]:
            crossed.add(c)
    return before, after, pending, crossed, ranks, reads


def bundle(rows):
    result = {}
    for field in FIELDS:
        by_tier = {t: sum(v[field][t] for v in rows) for t in ("cpu", "cuda")}
        n = sum(by_tier.values())
        result[field] = dict(
            by_tier=by_tier, jobs=n, payload_bytes=n * PAYLOAD, requested_bytes=n * WINDOW
        )
    return result


def original_reads(calls, reads):
    result = {}
    for name in ("cpu", "cuda"):
        c = sum((reads[(n, name)] for n in calls), Counter())
        result[name] = {
            k: c[k] for k in ("jobs", "payload_bytes", "requested_bytes", "returned_bytes")
        }
    return result


def sets_at_cuts(groups, before, after, ranks, reads, first_final):
    all_rows, early, atomic, reports = [], [], [], []
    for tag, calls in groups:
        if tag != "anchor":
            continue
        b, e = calls[0], calls[-1]
        src, dst = before[b][1], after[e][1]
        union = {key for n in calls for key in ranks[n]}
        full = measure_sets(src, dst, union)
        all_rows.append(full)
        item = {
            "calls": [b, e],
            "known_input_rows": len(calls),
            "off_trajectory_rows_unpriced": 3 - len(calls),
            "entry_sha256": before[b][0],
            "exit_sha256": after[e][0],
            "acquisition_floor": bundle([full]),
            "original_pack_reads": original_reads(calls, reads),
        }
        if e <= first_final:
            early.append(full)
            atomic.append(full)
        elif b <= first_final:
            # Neither premature delivery nor an atomic evaluation needs the final R0
            # carry until the block actually returns. Don't charge it at this text cut.
            prefix = {key for n in calls if n <= first_final for key in ranks[n]}
            truncated = measure_sets(src, set(), prefix)
            completed_math = measure_sets(src, set(), union)
            early.append(truncated)
            atomic.append(completed_math)
            item["partial_cut"] = {
                "through_call": first_final,
                "known_input_rows": first_final - b + 1,
                "early_delivery": bundle([truncated]),
                "all_inputs_before_delivery": bundle([completed_math]),
                "restore_charged": False,
            }
        reports.append(item)
    check(len(all_rows) == 11 and len(early) == len(atomic) == 10, "window coverage")
    return reports, {
        "decode": bundle(all_rows),
        "first_final": bundle(early),
        "first_final_atomic": bundle(atomic),
    }


def price(totals, study, num_anchors):
    out = {}
    for bound in ("end_carry", "joint"):
        for byte_field in ("payload_bytes", "requested_bytes"):
            for bps in (4_500_000_000, 8_000_000_000):
                ns = totals[bound][byte_field] * 10**9 // bps
                budgets = {}
                for label, original in study.items():
                    budgets[label] = {}
                    for percent, pay in original["fractions"].items():
                        check(original["anchors_to_charge"] == num_anchors, "verify count")
                        left = pay["budget_for_all_verification_and_overheads_ns"] - ns
                        budgets[label][percent] = {
                            "total_remaining_ns": left,
                            "mean_remaining_ns": left // num_anchors,
                            "status": "NO_GO_FIXED_SCENARIO" if left < 0 else "HEADROOM_ONLY",
                        }
                out[f"{bound}/{byte_field}/{bps}_Bps"] = {
                    "verification_io_floor_ns": ns,
                    "net": budgets,
                }
    return out


def assess(root, family_hash):
    family, arm, receipt, sealed = REOPEN["chain"](root, family_hash)
    on = root / "ON"
    audited = NATURAL["audit_arm"](on, receipt, receipt["pack_events"]["before_second_ns"])
    check(
        json.loads(json.dumps(audited)) == sealed
        and audited["status"] == "PASS_PACK_NATURAL_TRACE",
        "sealed complete audit",
    )
    events, header = NATURAL["PFJ"]["read_journal"](on / "raw/events.pfj")
    check(header == audited["header"], "PFJ reopened")
    h = NATURAL["host_trace"](events)
    log_name = receipt["native_ids"]["raw_stderr_file"]
    check(Path(log_name).name == log_name, "producer name")
    log = (on / "raw" / log_name).read_bytes()
    check(
        hashlib.sha256(log).hexdigest() == receipt["native_ids"]["stderr_sha256"], "producer seal"
    )
    tier_path = HERE.parents[1] / "tier_budget/score.py"
    placements, cache_mib = run_path(str(tier_path))["mapping"](log, events)
    check(
        placements == {i: ("CPU" if tier(i) == "cpu" else "CUDA0") for i in range(36)},
        "actual tiers",
    )
    actions = LOOKUP["partition"](on, receipt)
    g = blocks(actions)
    before, after, pending, crossed, ranks, reads = census(
        events, audited["first_decode"]["sha256"], len(actions)
    )
    for e in events:
        if e.kind in (13, 16, 17, 30) and 1 <= e.call <= len(actions):
            call = h["calls"][e.call - 1]
            start = e.begin if e.kind in (16, 30) else e.ns
            if not (call["enter_ns"] <= start <= e.ns <= call["return_ns"]):
                crossed.add(e.call)
    cut = audited["http_cut"]["sample_call"]
    check(cut == 46 and audited["http_cut"]["sample_number"] == 45, "client cut")
    result = dict(
        family_sha256=family_hash,
        arm_sha256=family["arms"]["ON"]["sha256"],
        receipt_sha256=arm["receipt_sha256"],
        journal_sha256=header["journal_sha256"],
        route=h["route"],
        clock_transfer=family["paired"]["clock_transfer"],
        placement_review_sha256=REOPEN["digest"](tier_path),
        expert_pool_mib=cache_mib,
        bytes_to_wall_scope="ALL_SELECTED_BYTES_TRAVERSE_ONE_CAPPED_RESOURCE_INSIDE_SERIAL_VERIFY_ENVELOPES",
        unknown_rejected_rows_charged=0,
        protocol_sha256=REOPEN["digest"](HERE / "protocol.md"),
        source_sha256=REOPEN["digest"](Path(__file__)),
        lookup_sha256=REOPEN["digest"](HERE.parent / "screen.py"),
        original_prefill={str(n): original_reads([n], reads) for n in (1, 2)},
        original_retained_ar=original_reads([c[0] for tag, c in g if tag == "ar"], reads),
        pending_calls=sorted(pending),
        crossing_calls=sorted(crossed),
    )
    if pending or crossed:
        return result | {"status": "INCONCLUSIVE_NON_DRAINED_EXTERNAL_CUT"}
    observed = audited["jobs"]["counts"]
    for field, key in (
        ("attempts", "jobs"),
        ("requested_bytes", "requested_bytes"),
        ("returned_bytes", "returned_bytes"),
    ):
        check(
            sum(x[key] for x in reads.values()) == observed[field],
            "all observed pack reads conserved",
        )
    reports, totals = sets_at_cuts(g, before, after, ranks, reads, cut)
    for block in reports:
        for t in ("cpu", "cuda"):
            check(
                block["acquisition_floor"]["joint"]["by_tier"][t]
                <= block["original_pack_reads"][t]["jobs"],
                "AR witness violates required acquisitions",
            )
    s = LOOKUP["savings"](h["calls"], h["callback_spans"], actions)
    public = receipt["rows"][1]
    priced = {}
    for name, volumes in totals.items():
        first = name.startswith("first_final")
        native = s[:46] if first else s[2:]
        observed_ns = math.floor(10**9 * public["first_final_s" if first else "decode_s"])
        target = 10**10 if first else (47_000_000_000 + 5) // 6
        limits = {
            k: LOOKUP["price"](native, observed_ns, target, free)
            for k, free in (("fixed_outside", False), ("free_outside", True))
        }
        priced[name] = price(volumes, limits, 10 if first else 11)
    return result | {
        "status": "MEASURED_AR_CUTS_CONDITIONAL_B3_VOLUME",
        "blocks": reports,
        "totals": totals,
        "price": priced,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--family-dir", type=Path, required=True)
    p.add_argument("--family-sha256", required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        report = assess(a.family_dir, a.family_sha256)
    except Exception as exc:
        tb = exc.__traceback__
        while tb.tb_next:
            tb = tb.tb_next
        report = {
            "status": "FAIL_PRESERVED",
            "family_sha256": a.family_sha256,
            "error": type(exc).__name__,
            "location": [Path(tb.tb_frame.f_code.co_filename).name, tb.tb_lineno],
        }
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(report, f, sort_keys=True, indent=2)
        f.write("\n")
    print(report["status"])
    return int(report["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
