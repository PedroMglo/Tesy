"""Optimistic cardinality-constrained bank coverage on four authenticated request clocks."""

import argparse
import hashlib
from collections import defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
COMBO = run_path(str(HERE.parent / "bank/score.py"))
SER, COST = COMBO["SER"], COMBO["BANK"]
Q, T, check = SER["Q"], SER["T"], SER["check"]
CAP = 353
METHOD = "37873c82361ea1eeb6538655f8a12ad1b8bac7d87abc3e7f57a8a50bb09a49b4"
BANK_SHA = "667700adf58f9b05fbb70884feedd8a0546883909cfee3a403445d8dcd2c955e"
LABELS = ("P97.first", "P97.decode", "P106.first", "P106.decode")


def coverage(waves, actions, offered, split, offset, features):
    sources = set()
    for wave in waves:
        if wave.start_drained:
            sources.clear()
        sources.update(key for r in wave.reserved if (key := COST["expert"](r)) in offered)
        call, _, layer, _ = wave.site
        retained = not split or actions[call - 1] not in {"anchor", "skip"} or layer >= 25
        if retained and sources:
            item = features.setdefault(frozenset(sources), [0] * 4)
            length = wave.end - wave.start
            if call <= 46:
                item[offset] += length
            if call >= 3:
                item[offset + 1] += length
        if wave.end_drained:
            sources.clear()


def gains(features, bank):
    return [sum(v[i] for keys, v in features.items() if keys & bank) for i in range(4)]


def greedy(features, weights, cap):
    """Weighted greedy with exact integer deltas and stable layer/expert tie-breaking."""
    owners = defaultdict(set)
    values = {}
    marginal = defaultdict(int)
    for keys, v in features.items():
        weight = sum(x * y for x, y in zip(weights, v, strict=True))
        if not weight:
            continue
        values[keys] = weight
        for key in keys:
            owners[key].add(keys)
            marginal[key] += weight
    result = []
    while len(result) < cap and marginal:
        key = min(marginal, key=lambda k: (-marginal[k], k))
        if marginal[key] == 0:
            break
        result.append(key)
        del marginal[key]
        for item in owners[key]:
            value = values.pop(item, 0)
            for member in item:
                if member in marginal:
                    marginal[member] -= value
    return result


def upper_bound(features, chosen, cap, dim):
    covered = 0
    rest = defaultdict(int)
    union = sum(v[dim] for v in features.values())
    for keys, v in features.items():
        if keys & chosen:
            covered += v[dim]
        else:
            for key in keys:
                rest[key] += v[dim]
    return min(union, covered + sum(sorted(rest.values(), reverse=True)[:cap]))


def solve(features, margins, controls):
    weights = [
        (1, 0, 0, 0),
        (0, 0, 1, 0),
        (0, 1, 0, 0),
        (0, 0, 0, 1),
        (1, 0, 1, 0),
        (1, 1, 1, 1),
        (2, 1, 2, 1),
        (0, 0, 2, 1),
    ]
    upper = [upper_bound(features, set(), CAP, i) for i in range(4)]
    options = {}
    for wt in weights:
        order = greedy(features, wt, CAP)
        bank = set(order)
        actual = gains(features, bank)
        for k in (64, 160, CAP):
            subset = set(order[:k])
            upper = [min(upper[i], upper_bound(features, subset, CAP, i)) for i in range(4)]
        options[wt] = (order, [m + g for m, g in zip(margins, actual, strict=True)])
    best = max(options, key=lambda wt: (min(options[wt][1]), sum(options[wt][1])))
    order, result = options[best]
    cap_margins = [m + g for m, g in zip(margins, upper, strict=True)]
    check(all(a <= b for a, b in zip(result, cap_margins, strict=True)), "invalid upper bound")
    if min(result) >= 0:
        verdict = "HEADROOM_ONLY"
    elif min(cap_margins) < 0:
        verdict = "NO_GO_FIXED_SCENARIO"
    else:
        verdict = "INCONCLUSIVE"
    return {
        "status": verdict,
        "clocks": LABELS,
        "before_bank_margin_ns": margins,
        "independent_upper_margin_ns": cap_margins,
        "all_offered_margin_ns": [
            m + sum(v[i] for v in features.values()) for i, m in enumerate(margins)
        ],
        "common_witness": {
            "margin_ns": result,
            "width": len(order),
            "weights": best,
            "ordered_sha256": hashlib.sha256(COMBO["serialized"](order)).hexdigest(),
        },
        "causal_margin_ns": {
            name: [m + g for m, g in zip(margins, gains(features, b), strict=True)]
            for name, b in controls.items()
        },
        "covered_feature_sets": len(features),
    }, order


def run(archive, marginal_path):
    check(Q["digest"](HERE / "protocol.md") == METHOD, "protocol")
    marginal = Q["pinned"](marginal_path, BANK_SHA)
    serial = Q["pinned"](HERE.parent / "receipt.json", COMBO["H"]["serial_receipt"])
    roots = {k: archive / ("part-" + k[1:]) / v[0] for k, v in COST["SOURCES"].items()}
    sel, new_rows, _, source = Q["read_new"](roots["P106"], SER["P106"])
    controls = {name: set(map(tuple, data["ordered_keys"])) for name, data in sel["banks"].items()}
    offered = set(map(tuple, sel["offered_keys"]))
    check(all(len(c) == CAP and c <= offered for c in controls.values()), "bank membership")
    fam = Q["pinned"](roots["P106"] / "family.json", SER["P106"])
    arm = Q["pinned"](roots["P106"] / "ON/arm.json", fam["arms"]["ON"]["sha256"])
    new = Q["pinned"](roots["P106"] / "ON/receipt.json", arm["receipt_sha256"])
    _, _, old, audit = Q["CHAIN"]["chain"](roots["P97"], Q["P97"])
    old_rows, hdr = T["PFJ"]["read_journal"](roots["P97"] / "ON/raw/events.pfj")
    check(hdr == audit["header"], "P97 journal")
    reports, witnesses = {}, {}
    for mode in ("split", "ordinary_AR"):
        features, margins = {}, []
        for pos, (label, rows, rec) in enumerate((("P97", old_rows, old), ("P106", new_rows, new))):
            actions = SER["LOOKUP"]["partition"](roots[label] / "ON", rec)
            waves, jobs = COST["timeline"](rows)
            check(len(waves) == 2987 and len(jobs) == 2354, "whole request")
            observed = marginal[label]
            if mode == "split":
                sc = serial[label]["suffix_to_return"]
                margins.extend(
                    sc[phase]["fractions"]["0"]["total_available_ns"]
                    for phase in ("first", "decode")
                )
            else:
                margins.extend(
                    (10**10 - observed["first_final_ns"], COST["ALLOW"] - observed["decode_ns"])
                )
            coverage(waves, actions, offered, mode == "split", 2 * pos, features)
            for name, bank in controls.items():
                gain = gains(features, bank)[2 * pos : 2 * pos + 2]
                if mode == "split":
                    s = observed["banks"][name]["prices"]["drained"]["suffix_to_return"]["free"]
                    expected = [s["first_new_cost_budget_ns"], s["decode_new_cost_budget_ns"]]
                    check(
                        [a + b for a, b in zip(gain, margins[-2:], strict=True)] == expected,
                        "joint causal controls",
                    )
                else:
                    phases = COST["bound"](waves, bank, True, 0)[0]
                    check(
                        gain
                        == [
                            sum(phases[p]["callback_ns"] for p in group)
                            for group in (
                                ("prefill", "decode_first"),
                                ("decode_first", "decode_tail"),
                            )
                        ],
                        "AR controls",
                    )
        reports[mode], witnesses[mode] = solve(features, margins, controls)
    return (
        {
            "status": "TRACE_DERIVED_OPTIMISTIC_COVERAGE",
            "offers_distinct": len(offered),
            "T1_source": source,
            "methods": {
                "protocol": METHOD,
                "code": Q["digest"](Path(__file__)),
                "intersection": BANK_SHA,
            },
            "regimes": reports,
        },
        witnesses,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", required=True, type=Path)
    p.add_argument("--intersection", required=True, type=Path)
    p.add_argument("--new-output-dir", required=True, type=Path)
    args = p.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        report, witnesses = run(args.archive, args.intersection)
        (args.new_output_dir / "witnesses.json").write_bytes(COMBO["serialized"](witnesses))
    except Exception as exc:
        report = {"status": "INCONCLUSIVE", "reason": str(exc), "error": type(exc).__name__}
    (args.new_output_dir / "receipt.json").write_bytes(COMBO["serialized"](report))
    print(report["status"])
    raise SystemExit(int(report["status"] == "INCONCLUSIVE"))
