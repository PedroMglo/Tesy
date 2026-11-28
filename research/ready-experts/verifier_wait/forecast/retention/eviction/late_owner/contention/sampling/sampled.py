"""Bracket each original NVMe pread with positive, externally observed syscall samples."""

import argparse
import json
import math
import os
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent
D = run_path(HERE.parent / "depths.py")
need, sha, save, M, IO = (D[k] for k in ("need", "sha", "save", "M", "IO"))
METHOD = "1f3c12401f5c4d6bb1f8b864ad2f036989fc5a0de51863b363f3760d5e916a82"
PRIOR = HERE.parent / "evidence-depths-20261128-r01"
SURFACE = "c3efeedb791c1efaea793d1b2892f6ab85d17eff648a27466b136a6416877ad5"
SELECTION = "46de23ac00240882f63c927625c143b97853806f567350c5e95b099d22383724"
TARGETS = ("2/1", "4/1")
TRIPLES = ("3/1", "3/2")
THREE_METHOD = "97cd21119042b48bc52dbdbf2196c013439eb4cc3e390e1a8009eb421ccf6ff5"
PAST = HERE / "evidence-20261128-r01"
PAST_SHA = "0398d782be84b7eb25851bda90a63d0d76552b15291d5b8a04c538afd0a6500b"
PPM = D["PPM"]
PAIRS = 31
ROWS = 4 * (2 + 4 * PAIRS)


def choose(tx, common, targets=TARGETS):
    def keys(ordinals):
        return [128 * tx[i - 1][2] + tx[i - 1][5] for i in ordinals]

    groups = {}
    for shape in targets:
        candidates = sorted(common[shape])
        need(candidates, "missing original population")
        first = candidates[0]
        slots = [("first", 0)]
        middle = len(candidates) // 2
        own = set(keys(first))
        for n in range(len(candidates)):
            idx = (middle + n) % len(candidates)
            if set(keys(candidates[idx])) != own:
                slots.append(("holdout", idx))
                break
        for label, idx in slots:
            cohort = candidates[idx]
            groups[f"{shape}-{label}"] = dict(
                shape=shape,
                sample=label,
                index=idx,
                common=len(candidates),
                ordinals=list(cohort),
                keys=keys(cohort),
            )
    return groups


def plan(args, targets=TARGETS):
    if targets == TRIPLES:
        prev = M["verified"](PAST / "projection.json", PAST_SHA)
        envelope = prev["models"]["envelope"]
        need(
            prev["status"] == "INCONCLUSIVE"
            and tuple(k for k, v in envelope["rates_ppm"].items() if v == [0, PPM]) == TRIPLES,
            "remaining unmeasured populations",
        )
    else:
        prev = M["verified"](PRIOR / "projection.json", SURFACE)
        selection = M["verified"](PRIOR / "thresholds.json", SELECTION)
        need(
            prev["status"] == "INCONCLUSIVE"
            and selection["ranges"]["high"]["minimal_passing_sets"] == [list(TARGETS)],
            "admission",
        )
    tx, common, _, _ = D["populations"]()
    groups = choose(tx, common, targets)
    old = M["verified"](
        PRIOR / "device.json", "99435971e44f29ca866c75b8cdfa016d652f9cc81ea2a795e1d023689f2c8cc3"
    )
    for shape in targets:
        original = old["plan"]["groups"][shape]
        got = groups[f"{shape}-first"]
        need(all(got[k] == original[k] for k in ("keys", "ordinals", "common")), "original parity")
    return D["pack_plan"](args, groups, lambda q, k: (ROWS + 1) * q - ROWS // 2 * k)


def build(args):
    prelude = HERE.parent / "peer.cpp"
    need(sha(prelude) == D["PRELUDE"], "authenticated native reader")
    pre, sep, _ = prelude.read_text().partition("struct Trial {")
    need(bool(sep), "prelude boundary")
    src = args.new_output_dir / "sampled.cpp"
    with src.open("x") as f:
        f.write(pre + (HERE / "worker.cpp.in").read_text())
    return D["DEV"]["build"](args, reader_source=src)


def schedule():
    for stage in range(4):
        orders = [(-1, 0)]
        for p in range(1, PAIRS + 1):
            first = (p - 1) % 2
            orders.extend(((first, p), (1 - first, p)))
        for order, p in orders:
            for leg in range(2):
                alternate = int((order == 1) != bool(leg))
                yield (
                    stage,
                    order,
                    p,
                    stage if stage < 2 else alternate,
                    alternate if stage < 2 else int(stage == 3),
                )


def bounds(measure, peers, observed):
    n, a, b, c, d, returned = measure
    if not observed:
        need(not any(measure), "OFF queried individual clocks")
        return None
    need(returned > 0 and n >= 0, "unseen return flag")
    if n == 0:
        need(a == b == c == d == 0, "unobserved syscall with marks")
    elif n == 1:
        need(0 <= a == c <= b == d <= returned, "single sample ordering")
    else:
        need(0 <= a <= b <= c <= d <= returned, "positive samples out of order")
    lo = max(0, c - b)
    hi = min(returned, peers)
    need(0 <= lo <= hi and hi > 0, "inverted duration interval")
    return lo, hi, n


def median_lower(values):
    # None represents minus infinity when the denominator has no positive lower bound.
    unknown = values.count(None)
    middle = len(values) // 2
    return (
        None if unknown > middle else sorted(v for v in values if v is not None)[middle - unknown]
    )


def interval_reduction(d, h):
    need(0 <= d[0] <= d[1] and d[1] > 0 and 0 <= h[0] <= h[1], "pair bounds")
    low = 1 - Fraction(h[1], d[0]) if d[0] else None
    return low, 1 - Fraction(h[0], d[1])


def rational(value):
    return None if value is None else [value.numerator, value.denominator]


def class_grade(pairs, misses):
    checks, off, lanes = [], [], []
    low_bound, high_bound = PPM, 0
    for order in (0, 1):
        for stage in (0, 1):
            rows = [pairs[stage, order, p] for p in range(1, PAIRS + 1)]
            checks.append(median(Fraction(v[1][0][0], v[0][0][0]) for v in rows))
        rows = [pairs[2, order, p] for p in range(1, PAIRS + 1)]
        off.append([median(v[1][0][i] - v[0][0][i] for v in rows) for i in range(3)])
        rows = [pairs[3, order, p] for p in range(1, PAIRS + 1)]
        for w in range(misses):
            samples = [(v[0][1][w], v[1][1][w]) for v in rows]
            changes = [interval_reduction(d, h) for d, h in samples]
            low = median_lower([v[0] for v in changes])
            high = median(v[1] for v in changes)
            need(low is None or low <= high, "ordered paired medians")
            low_bound = min(
                low_bound, 0 if low is None else max(0, min(PPM, math.floor(low * PPM)))
            )
            high_bound = max(high_bound, max(0, min(PPM, math.ceil(high * PPM))))
            coverage = []
            for s in (0, 1):
                leg = [x[s] for x in samples]
                coverage.append(
                    dict(
                        positive_duration=sum(x[0] > 0 for x in leg),
                        queries_matched=sum(x[2] for x in leg),
                        min_matches=min(x[2] for x in leg),
                        median_width_ns=median(x[1] - x[0] for x in leg),
                        median_lower_ns=median(x[0] for x in leg),
                        median_upper_ns=median(x[1] for x in leg),
                    )
                )
            lanes.append(
                dict(order=order, lane=w, reduction=[rational(low), rational(high)], DH=coverage)
            )
    neutral = all(Fraction(97, 100) <= v <= Fraction(103, 100) for v in checks)
    return dict(
        neutral=neutral,
        median_ON_over_OFF=list(map(rational, checks)),
        OFF_H_minus_D_ns=off,
        lanes=lanes,
        observed_ppm=[low_bound, high_bound],
        reduction_ppm=[low_bound, high_bound] if neutral else [0, PPM],
    )


def parse(lines, plan, targets=TARGETS):
    labels = plan["labels"]
    need(
        labels
        == [
            f"{s}-{kind}"
            for s in targets
            for kind in ("first", "holdout")
            if f"{s}-{kind}" in plan["groups"]
        ]
        and len(lines) == 2 + (ROWS + 1) * len(labels)
        and lines[0].split() == ["fd", *map(str, plan["pack_stat"])]
        and lines[-1] == "drained",
        "fd, cohorts or extent",
    )
    groups = {}
    total = hashes = 0
    for g, label in enumerate(labels):
        q, k = map(int, plan["groups"][label]["shape"].split("/"))
        need(f"{q}/{k}" == label.split("-")[0] and 0 < k < q <= 4, "target groups")
        misses = q - k
        pairs = defaultdict(dict)
        base = 1 + (ROWS + 1) * g
        for i, spec in enumerate(schedule()):
            tag, *fields = lines[base + i].split()
            zs = list(map(int, fields))
            need(
                tag == "row" and len(zs) == 9 + 6 * misses and zs[:6] == [g, *spec],
                "schedule or worker schema",
            )
            stage, order, p, hit, obs = spec
            clocks = zs[6:9]
            need(0 < clocks[0] <= clocks[1] <= clocks[2], "consumer clocks")
            durations = [bounds(zs[9 + 6 * w : 15 + 6 * w], clocks[0], obs) for w in range(misses)]
            key = obs if stage < 2 else hit
            pair = pairs[stage, order, p]
            need(key not in pair, "repeated leg")
            pair[key] = clocks, durations
        kind, *tail = lines[base + ROWS].split()
        requested = [ROWS + 1] * misses + [ROWS // 2 + 1] * k + [0] * (4 - q)
        checked = [3 * (ROWS + 1)] * q + [0] * (4 - q)
        need(
            kind == "closed" and list(map(int, tail)) == [g, *requested, *checked],
            "physical conservation",
        )
        groups[label] = class_grade(pairs, misses)
        total += sum(requested)
        hashes += sum(checked)
    need(total == plan["expected_records"], "descriptor volume")
    return dict(
        groups=groups,
        requested_records=total,
        hashes=hashes,
        trials=ROWS * len(labels),
        model_forwards=0,
    )


def projection(timing, spec, targets=TARGETS):
    old = M["verified"](PRIOR / "projection.json", SURFACE)
    prev = M["verified"](PRIOR / "mixed.json", D["MIXED"])
    tx, common, by_arm, hits = D["populations"]()
    need(choose(tx, common, targets) == spec["groups"], "cohort selection")
    need(D["reprice_rates"](old["rates_ppm"], by_arm, hits, prev) == old, "historical control")
    parent = None
    if targets == TRIPLES:
        parent = M["verified"](PAST / "projection.json", PAST_SHA)
        meta = json.loads((PAST / "device.json").read_bytes())
        need(sha(PAST / "service.txt") == meta["stdout_sha256"], "antecedent clock identity")
        prior_timing = parse((PAST / "service.txt").read_text().splitlines(), meta["plan"])
        need(
            prior_timing == meta["timing"] and projection(prior_timing, meta["plan"]) == parent,
            "prior populations and client clocks",
        )

    def values(shape, sample):
        return timing["groups"].get(f"{shape}-{sample}", {}).get("reduction_ppm", [0, PPM])

    models = {}
    for kind in ("first", "holdout", "envelope"):
        rates = dict(parent["models"][kind]["rates_ppm"] if parent else old["rates_ppm"])
        for shape in targets:
            a, b = values(shape, "first"), values(shape, "holdout")
            rates[shape] = {
                "first": a,
                "holdout": b,
                "envelope": [min(a[0], b[0]), max(a[1], b[1])],
            }[kind]
        models[kind] = D["reprice_rates"](rates, by_arm, hits, prev)
    return dict(
        method=THREE_METHOD if parent else METHOD,
        earlier=PAST_SHA if parent else SURFACE,
        status=models["envelope"]["status"],
        models=models,
        http_requests=0,
        evidence="MEASURED_DEVICE_TRACE_DERIVED_CLIENT",
    )


def physical(a, receipt, *, triples=False):
    IO["run"](
        a,
        receipt,
        protocol=THREE_METHOD if triples else METHOD,
        source=HERE / ("three-protocol.md" if triples else "protocol.md"),
        parse=lambda lines, spec: parse(lines, spec, TRIPLES if triples else TARGETS),
        maximum_bytes=65_000_000_000 if triples else 72_000_000_000,
        requested_records=lambda t, _: t["requested_records"],
    )


def main(*, triples=False):
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest="action", required=True)
    for task, fields in (
        ("plan", ("manifest",)),
        ("build", ("previous",)),
        ("grade", ("observed", "plan")),
    ):
        q = subs.add_parser(task)
        for field in (*fields, "new-output-dir"):
            q.add_argument("--" + field, type=lambda v: Path(v).resolve(), required=True)
    subs.add_parser("check").add_argument("evidence", type=Path)
    args = p.parse_args()
    targets, method, document = (
        (TRIPLES, THREE_METHOD, "three-protocol.md")
        if triples
        else (TARGETS, METHOD, "protocol.md")
    )
    need(sha(HERE / document) == method, "registered method")
    if args.action == "check":
        e = args.evidence
        meta = json.loads((e / "device.json").read_bytes())
        timing = parse((e / "service.txt").read_text().splitlines(), meta["plan"], targets)
        need(
            sha(e / "service.txt") == meta["stdout_sha256"] and timing == meta["timing"],
            "public device clocks",
        )
        result = projection(timing, meta["plan"], targets)
        need(
            result == json.loads((e / "projection.json").read_bytes()), "public request projection"
        )
        print(result["status"], result["models"]["envelope"]["margins_ns"])
        return
    os.umask(0o077)
    args.new_output_dir.mkdir()
    try:
        commit, tree = M["B"]["version"]()
        if args.action == "grade":
            obs = json.loads((args.observed / "receipt.json").read_bytes())
            need(
                obs["status"] == "MEASURED"
                and (obs["commit"], obs["tree"], obs["protocol"]) == (commit, tree, method)
                and sha(args.observed / "stdout") == obs["stdout_sha256"],
                "physical identity",
            )
            spec = M["verified"](args.plan / "receipt.json", obs["plan_sha256"])
            timing = parse((args.observed / "stdout").read_text().splitlines(), spec, targets)
            need(timing == obs["timing"], "private clock reproduction")
            result = projection(timing, spec, targets)
            save(args.new_output_dir / "projection.json", result)
            print(result["status"], result["models"]["envelope"]["margins_ns"])
        else:
            result = plan(args, targets) if args.action == "plan" else build(args)
            save(
                args.new_output_dir / "receipt.json",
                result
                | dict(
                    status="PASS",
                    commit=commit,
                    tree=tree,
                    protocol=method,
                    program=sha(Path(__file__)),
                ),
            )
            print("PASS", sha(args.new_output_dir / "receipt.json"))
    except Exception as exc:
        save(args.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=repr(exc)))
        raise


if __name__ == "__main__":
    main()
