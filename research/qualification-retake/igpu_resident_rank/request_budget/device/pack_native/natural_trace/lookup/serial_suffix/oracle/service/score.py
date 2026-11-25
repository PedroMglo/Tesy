"""Price two sealed banks and certify optimistic margin bounds for every offered K353 bank."""

import argparse
import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
ORACLE = run_path(str(HERE.parent / "oracle.py"))
COMBO, COST = ORACLE["COMBO"], ORACLE["COST"]
Q, T, check = ORACLE["Q"], ORACLE["T"], ORACLE["check"]
serialized = COMBO["serialized"]
CAP = ORACLE["CAP"]
PPM = 1_000_000
SCALES = (0, PPM // 2, PPM)
PROTOCOL = "083ddaaf59cce39d95105f8ba221a791f0d83451c62856a2f4552c1134d6fddb"
CODE = "4e444d13bff35b0da68c461150a75c505be88e257eaf00eb3e7618095b99b65a"
CAP_REPORT = "615d5aa5f55bfdeeead270942ee2c4b2909dcfa7afe6a938891bfe56141b05c9"
WITNESSES = "e2e8daca3341a6556379280a8a90adabf2a439367565c1120afd1094f13e692b"
CLOCKS = ORACLE["LABELS"]
PHASES = ("prefill", "decode_first", "decode_tail")


@dataclass(frozen=True)
class Event:
    width: int
    sources: frozenset
    jobs: tuple
    phase: str


def events(waves, actions, offered, split):
    recent = set()
    result = []
    for w in waves:
        if w.start_drained:
            recent.clear()
        recent.update(k for j in w.reserved if (k := COST["expert"](j)) in offered)
        call, _, layer, _ = w.site
        retained = not split or layer >= 25 or actions[call - 1] not in ("anchor", "skip")
        if retained and recent:
            work = tuple((COST["expert"](j), v) for j, v in sorted(w.required_service.items()))
            check(
                w.required_service.keys() == w.reserved & w.demands
                and all(k not in offered or k in recent for k, _ in work)
                and COST["RELEASE"]["four_lanes"]([v for _, v in work]) <= w.end - w.start,
                "own released, consumed and priced work",
            )
            result.append(Event(w.end - w.start, frozenset(recent), work, COST["phase"](call)))
        if w.end_drained:
            recent.clear()
    return result


def floor(jobs, bank):
    return COST["RELEASE"]["four_lanes"]([v for k, v in jobs if k not in bank])


def exact(covered, scale):
    return sum(width - scale * price // PPM for width, price in covered)


def support(e, scale, offered, reference, mode):
    """Nonnegative coverage majorant; selecting a job's eligible key covers its own wave."""
    if mode == "never_offered":
        base = scale * floor(e.jobs, offered) // PPM
        return e.width - base, {}
    remaining = [(k, v) for k, v in e.jobs if k not in reference]
    if not remaining:
        remaining = list(e.jobs)
    single = max(remaining, key=lambda pair: pair[1], default=(None, 0))
    if single[1] >= sum(v for _, v in remaining) // 4:
        amounts = [(single[0], scale * single[1] // PPM)]
    else:
        amounts = [(k, scale * v // (4 * PPM)) for k, v in e.jobs]
    bonuses = Counter()
    for k, value in amounts:
        if value and k in offered:
            bonuses[k] += value
    return e.width - sum(p for _, p in amounts), bonuses


def cover_upper(features, cap, anchors):
    """Integer dual certificate. Charge a feature once for free or to each covering key."""
    features = {k: v for k, v in features.items() if v}
    total = sum(features.values())
    if not total:
        return 0
    upper = total
    for anchor in (set(), *anchors):
        fixed = 0
        loads = Counter()
        for keys, value in features.items():
            if keys & anchor:
                fixed += value
            else:
                for k in keys:
                    loads[k] += value
        upper = min(upper, fixed + sum(sorted(loads.values(), reverse=True)[:cap]))
    singleton = Counter()
    multiple = []
    for keys, value in features.items():
        if len(keys) == 1:
            singleton[next(iter(keys))] += value
        else:
            multiple.append((sorted(keys), value))
    # Cap the amount distributed to a key, leaving the remainder of each feature free.
    # Different thresholds change tightness only. Every returned bound dominates every bank.
    priorities = (
        sorted(multiple, key=lambda x: (len(x[0]), -x[1], x[0])),
        sorted(multiple, key=lambda x: (-x[1], len(x[0]), x[0])),
    )
    for threshold in {total * i // (16 * cap) for i in range(1, 33)}:
        for order in priorities:
            loads = singleton.copy()
            free = 0
            for keys, weight in order:
                spread = min(weight, max(0, threshold - max(loads[k] for k in keys)))
                free += weight - spread
                if spread:
                    for k in keys:
                        loads[k] += spread
            upper = min(upper, free + sum(sorted(loads.values(), reverse=True)[:cap]))
    return upper


def certificate(population, offered, witness, scale, cap):
    anchors = [set(witness[:n]) for n in (64, 160, cap)]
    limits = {}
    for mode, ref in (
        ("never_offered", set()),
        ("all_jobs_support", set()),
        ("never_offered_support", offered),
        ("official_support", set(witness)),
    ):
        features = Counter()
        for e in population:
            value, bonuses = support(e, scale, offered, ref, mode)
            check(value >= 0, "negative base support")
            features[e.sources] += value
            for k, v in bonuses.items():
                features[frozenset((k,))] += v
        limits[mode] = cover_upper(features, cap, anchors)
    return limits


def threshold(fn):
    """Last feasible integer ppm and first failure on the preregistered [0,1] grid."""
    if fn(0) < 0:
        return {"max_feasible_ppm": None, "first_infeasible_ppm": 0}
    if fn(PPM) >= 0:
        return {"max_feasible_ppm": PPM, "first_infeasible_ppm": None}
    lo, hi = 0, PPM
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if fn(mid) >= 0:
            lo = mid
        else:
            hi = mid
    return {"max_feasible_ppm": lo, "first_infeasible_ppm": hi}


def cost_rows(population, bank, offered):
    counts = Counter()
    records = []
    for e in population:
        counts["offered_influence_eligible_callbacks"] += 1
        if e.sources.isdisjoint(bank):
            continue
        saved = {k for k, _ in e.jobs if k in bank}
        required = [v for k, v in e.jobs if k not in saved]
        cost = floor(e.jobs, bank)
        counts.update(
            {
                "affected_callbacks": 1,
                "gross_eligible_ns": e.width,
                "uncovered_jobs": len(required),
                "uncovered_never_offered_jobs": sum(k not in offered for k, _ in e.jobs),
                "uncovered_worker_service_ns": sum(required),
                "uncovered_floor_wall_ns": cost,
            }
        )
        records.append((e.width, cost))
    return records, counts


def get_populations(archive):
    roots = {k: archive / ("part-" + k[1:]) / v[0] for k, v in COST["SOURCES"].items()}
    root = roots["P106"]
    family = Q["pinned"](root / "family.json", COST["SOURCES"]["P106"][1])
    arm = Q["pinned"](root / "ON/arm.json", family["arms"]["ON"]["sha256"])
    receipt = Q["pinned"](root / "ON/receipt.json", arm["receipt_sha256"])
    selection, rows, _, provenance = Q["read_new"](root, COST["SOURCES"]["P106"][1])
    offered = set(map(tuple, selection["offered_keys"]))
    pop = {}
    for tag in ("P106", "P97"):
        root = roots[tag]
        if tag == "P97":
            _, _, receipt, audit = COST["CHAIN"]["chain"](root, Q["P97"])
            rows, header = T["PFJ"]["read_journal"](root / "ON/raw/events.pfj")
            check(header == audit["header"], "P97 trace")
        waves, jobs = COST["timeline"](rows)
        check((len(waves), len(jobs)) == (2987, 2354), "callback and reservation census")
        actions = ORACLE["SER"]["LOOKUP"]["partition"](root / "ON", receipt)
        pop[tag] = {
            mode: events(waves, actions, offered, mode == "split")
            for mode in ("split", "ordinary_AR")
        }
    return pop, offered, provenance


def solve(pop, offered, mode, order, regime):
    bank = set(order)
    check(len(bank) == len(order) == CAP and bank <= offered, "fixed legal witness")
    check(
        hashlib.sha256(serialized(order)).hexdigest() == regime["common_witness"]["ordered_sha256"],
        "ordered witness identity",
    )
    answer, phase_values = {}, {}
    data = []
    for idx, clock in enumerate(CLOCKS):
        tag, name = clock.split(".")
        keep = PHASES[:2] if name == "first" else PHASES[1:]
        ev = [e for e in pop[tag][mode] if e.phase in keep]
        covered, counts = cost_rows(ev, bank, offered)
        baseline = regime["before_bank_margin_ns"][idx]
        source_margin = regime["common_witness"]["margin_ns"][idx]
        prior_upper = regime["independent_upper_margin_ns"][idx]
        check(baseline + exact(covered, 0) == source_margin, "reopen free witness margin")
        measures = {}
        for s in SCALES:
            exact_margin = baseline + exact(covered, s)
            bounds = certificate(ev, offered, order, s, CAP) if s else {}
            upper_margin = min([prior_upper] + [baseline + v for v in bounds.values()])
            check(exact_margin <= upper_margin, "invalid universal bound")
            measures[str(s)] = {
                "fixed_margin_ns": exact_margin,
                "any_upper_margin_ns": upper_margin,
                "bounds_gain_ns": bounds,
            }
        answer[clock] = {
            "before_bank_margin_ns": baseline,
            "counts": counts,
            "scales_ppm": measures,
            "fixed_boundary": threshold(lambda s, b=baseline, rows=covered: b + exact(rows, s)),
        }
        data.append((baseline, covered, len(ev)))
    for tag in ("P97", "P106"):
        phase_values[tag] = {}
        for phase in PHASES:
            ev = [e for e in pop[tag][mode] if e.phase == phase]
            jobs, census = cost_rows(ev, bank, offered)
            phase_values[tag][phase] = {
                "counts": census,
                "credit_ns": {str(s): exact(jobs, s) for s in SCALES},
            }

    def joint(s):
        return min(b + exact(r, s) for b, r, _ in data)

    def universal(s):
        vals = []
        for key, (_, _, n) in zip(CLOCKS, data, strict=True):
            m = answer[key]["scales_ppm"]
            exact_grid = min(m[str(f)]["any_upper_margin_ns"] for f in SCALES if f <= s)
            first, last = (m[str(f)]["any_upper_margin_ns"] for f in (0, PPM))
            chord = ((PPM - s) * first + s * last) // PPM + n
            vals.append(min(first, exact_grid, chord))
        return min(vals)

    fixed = threshold(joint)
    at = fixed["first_infeasible_ppm"]
    if at is not None:
        fixed["first_failing_clocks"] = [
            k for k, (b, r, _) in zip(CLOCKS, data, strict=True) if b + exact(r, at) < 0
        ]
    cap_boundary = threshold(universal)
    return {
        "clocks": answer,
        "phases": phase_values,
        "fixed_joint": fixed,
        "any_necessary_boundary": {
            "max_not_excluded_ppm": cap_boundary["max_feasible_ppm"],
            "first_certified_no_go_ppm": cap_boundary["first_infeasible_ppm"],
        },
        "decisions": {
            str(s): (
                "HEADROOM_FOR_FIXED_WITNESS_ONLY"
                if joint(s) >= 0
                else "NO_OFFERED_K353_AT_FIXED_PRICES"
                if universal(s) < 0
                else "FIXED_WITNESS_FAIL_OTHER_SELECTION_UNKNOWN"
            )
            for s in SCALES
        },
    }


def run(archive, marginal, capacity_dir):
    check(Q["digest"](HERE / "protocol.md") == PROTOCOL, "protocol")
    check(Q["digest"](HERE.parent / "oracle.py") == CODE, "oracle implementation")
    expected = Q["pinned"](capacity_dir / "receipt.json", CAP_REPORT)
    private = Q["pinned"](capacity_dir / "witnesses.json", WITNESSES)
    marginal_data = COMBO["run"](archive)
    check(hashlib.sha256(serialized(marginal_data)).hexdigest() == ORACLE["BANK_SHA"], "AR clocks")
    reproduced, choices = ORACLE["run"](archive, marginal)
    check(
        serialized(reproduced) == serialized(expected)
        and serialized(choices) == serialized(private),
        "reproduced oracle receipt and witnesses",
    )
    pop, offered, provenance = get_populations(archive)
    check(
        len(offered) == expected["offers_distinct"] == 2829 and provenance == expected["T1_source"],
        "T1 offer universe",
    )
    return {
        "status": "REPRODUCED_FIXED_WITNESS_AND_SERVICE_CERTIFICATES",
        "identity": {
            "protocol_sha256": PROTOCOL,
            "code_sha256": Q["digest"](Path(__file__)),
            "oracle_code_sha256": CODE,
            "oracle_receipt_sha256": CAP_REPORT,
            "witnesses_sha256": WITNESSES,
            "prior_intersection_sha256": ORACLE["BANK_SHA"],
            "archives": marginal_data["provenance"],
        },
        "clock_order": CLOCKS,
        "cap": CAP,
        "t1_offered_distinct": len(offered),
        "regimes": {
            mode: solve(pop, offered, mode, order, reproduced["regimes"][mode])
            for mode, order in choices.items()
        },
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ("archive", "intersection", "capacity-dir", "new-output-dir"):
        p.add_argument("--" + flag, type=Path, required=True)
    args = p.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        report = run(args.archive, args.intersection, args.capacity_dir)
    except Exception as exc:
        report = {"status": "FAIL_PRESERVED", "reason": str(exc), "error": type(exc).__name__}
    (args.new_output_dir / "receipt.json").write_bytes(serialized(report))
    print(report["status"])
    raise SystemExit(int(report["status"] == "FAIL_PRESERVED"))
