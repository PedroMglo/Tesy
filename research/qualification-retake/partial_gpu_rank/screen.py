"""Integer certificates of conditional savings with fixed additional expert copies."""

import argparse
import hashlib
import itertools
import json
import resource
import signal
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "gpu_cohorts"))
import bound as cohorts  # noqa: E402

require = cohorts.c294.require
PROTOCOL = "86c0f111db1436c55098e00db1ce1da16d8250608c6a7a90c079ba04a966921f"
SOURCE = "9e4231c2c5ea6f341cb6b2c55239ca87f23fdcf8c551e4af442104d3910442ea"
EVIDENCE = "c24d25b56f935900db756fd0c9653893018e4a1fe23f34f08e53e1e92e4df452"


def extract(raw, baseline):
    marker, demands, worker = {}, defaultdict(list), defaultdict(dict)
    for line in raw.splitlines()[1:]:
        kind, stamp, call, route, layer, expert, slot, gen, comp, size, _ = map(int, line.split())
        if not call:
            continue
        group = call, layer
        if kind in (1, 2, 15, 16):
            marker[call, layer, kind] = stamp
        if layer not in range(25):
            continue
        if kind == 3:
            demands[group].append((expert, size, slot, gen, route))
        if kind in (4, 5, 6, 7, 8, 9, 10):
            key = call, layer, expert, slot, gen, route
            # A repeated enqueue can promote the same generation without starting a second read.
            if (comp, kind) in worker[key]:
                require(kind == 4, "duplicate worker phase")
                continue
            worker[key][comp, kind] = stamp
    jobs = defaultdict(list)
    for key, phases in worker.items():
        jobs[key[:3]].append((key, phases))
    broad, paid, counts = [], [], Counter()
    for call in range(1, 33):
        for layer in range(25):
            left = marker[call, layer, 1]
            router = marker[call, layer, 2]
            right = marker[call, layer + 1, 1 if layer < 24 else 2]
            require(left <= router <= right, "noncausal layer window")
            keys, chain = [], []
            for expert, state, slot, gen, route in demands[call, layer]:
                keys.append(128 * layer + expert)
                actual = jobs.pop((call, layer, expert), [])
                counts[("absent", "loading", "resident")[state]] += 1
                if state == 2:
                    require(not actual, "resident generated worker load")
                    chain.append(0)
                    continue
                require(len(actual) == 1, "miss needs one owned generation")
                key, phases = actual[0]
                require(key[-1] == route and (state == 0 or (slot, gen) == key[3:5]),
                        "changed miss identity")
                times = [phases[-1, 4], phases[-1, 5]]
                for comp in range(3):
                    times.extend(phases[comp, kind] for kind in (6, 7, 8, 9))
                times.append(phases[-1, 10])
                require(router <= times[0] <= times[-1] <= right and times == sorted(times),
                        "read crosses a release or derived deadline")
                chain.append(sum(max(0, phases[c, 7] - phases[c, 6] - 1) for c in range(3)))
            require(len(keys) == len(set(keys)) == 4, "CPU rank coverage")
            broad.append((tuple(keys), right - left + 1, (0, 0, 0, 0)))
            paid.append((tuple(keys), right - router + 1, tuple(chain)))
    require(not jobs, "orphan CPU work")
    require(sum(w - 1 for _, w, _ in broad) == baseline["CPU_intervals_us_before_rounding"],
            "different gross CPU intervals")
    return broad, paid, counts


def saving(group, selected):
    keys, width, chain = group
    if selected.isdisjoint(keys):
        return 0
    return width - max((d for key, d in zip(keys, chain, strict=True) if key not in selected),
                       default=0)


def greedy(groups, capacity):
    selected = set()
    for _ in range(capacity):
        gain = defaultdict(int)
        for group in groups:
            keys, width, chain = group
            old = saving(group, selected)
            for i, key in enumerate(keys):
                if key not in selected:
                    remaining = max((v for j, v in enumerate(chain)
                                     if j != i and keys[j] not in selected), default=0)
                    gain[key] += width - remaining - old
        if not gain:
            break
        best = max(gain, key=lambda key: (gain[key], -key))
        if not gain[best]:
            break
        selected.add(best)
    return selected, sum(saving(g, selected) for g in groups)


def relaxation(groups):
    weights, linear = [], Counter()
    for keys, width, chain in groups:
        require(len(keys) == len(set(keys)) == len(chain) == 4 and min(chain) >= 0
                and width >= max(chain), "invalid group")
        ordered = sorted(zip(chain, keys, strict=True), reverse=True)
        weights.append(12 * (width - ordered[0][0]))
        for j, (duration, _) in enumerate(ordered, 1):
            following = ordered[j][0] if j < 4 else 0
            value = (duration - following) * (12 // j)
            for _, key in ordered[:j]:
                linear[key] += value
    return weights, linear


def verify_prices(groups, capacity, prices):
    weights, scores = relaxation(groups)
    excess = 0
    for (keys, _, _), weight, price in zip(groups, weights, prices, strict=True):
        require(type(price) is int and 0 <= price <= weight, "invalid integer dual price")
        excess += weight - price
        for key in keys:
            scores[key] += price
    return excess + sum(sorted(scores.values(), reverse=True)[:capacity])


def certificate(groups, capacity, window):
    chosen, lower = greedy(groups, capacity)
    weights, linear = relaxation(groups)
    distinct = sorted(linear)
    index = {key: i for i, key in enumerate(distinct)}
    edges = [tuple(index[k] for k in g[0]) for g in groups]
    prices = weights.copy()
    best = None
    # Select valid prices by projected subgradient search. Every iterate is an upper bound.
    for iteration in range(160):
        scores = [linear[k] for k in distinct]
        for (a, b, c, d), p in zip(edges, prices, strict=True):
            scores[a] += p
            scores[b] += p
            scores[c] += p
            scores[d] += p
        top = sorted(range(len(scores)), key=scores.__getitem__, reverse=True)[:capacity]
        complement = sum(weights) - sum(prices)
        top_sum = sum(scores[i] for i in top)
        total = complement + top_sum
        require(total >= 12 * lower, "certificate contradicts feasible subset")
        if best is None or total < best[0]:
            best = total, complement, top_sum, prices.copy()
        selected = set(top)
        grad = [sum(i in selected for i in edge) - 1 for edge in edges]
        step = max(1, (total - 12 * lower) // max(1, sum(g*g for g in grad)) //
                   (1 + iteration // 32))
        prices = [max(0, min(w, p - step * g))
                  for w, p, g in zip(weights, prices, grad, strict=True)]
    upper, complement, top_sum, prices = best
    require(upper == verify_prices(groups, capacity, prices), "published dual verification")
    remaining = 12 * window - upper
    report = dict(greedy_keys=sorted(chosen), greedy_saving_us=lower,
                dual_upper_twelfths_us=upper, dual_constant=complement, dual_top64=top_sum,
                dual_prices_sha256=hashlib.sha256(json.dumps(prices).encode()).hexdigest(),
                remaining_floor_us=remaining / 12, six_excluded=6 * remaining > 384_000_000,
                greedy_touches_six=6 * (window - lower) <= 32_000_000)
    return report, prices


def test_certificate():
    toy = [((0, 1, 2, 3), 17, (2, 3, 7, 12)), ((0, 1, 2, 4), 11, (0, 8, 4, 4)),
           ((1, 2, 3, 4), 23, (0, 0, 3, 0))]
    for k in range(6):
        optimum = max(sum(saving(g, set(s)) for g in toy)
                      for s in itertools.combinations(range(5), k))
        result, _ = certificate(toy, k, 100)
        require(12 * result["greedy_saving_us"] <= 12 * optimum <= result["dual_upper_twelfths_us"],
                "exhaustive toy rejected certificate")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--new-output-dir", type=Path, required=True)
    args = parser.parse_args()
    resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
    signal.alarm(60)
    require(not args.new_output_dir.resolve().is_relative_to(args.raw_dir.resolve()), "protect raw")
    args.new_output_dir.mkdir(parents=True, exist_ok=False)
    cohorts.verified(HERE / "protocol.md", PROTOCOL)
    cohorts.verified(Path(cohorts.__file__), SOURCE)
    prior = json.loads(cohorts.verified(cohorts.HERE / "evidence-r3/receipt.json", EVIDENCE))
    require(prior["capacity"]["k_with_one_extra_mib"] == 64, "K")
    manifest = json.loads(cohorts.verified(cohorts.c294.MANIFEST, cohorts.c294.MANIFEST_SHA))
    entries = {x["path"].split("/raw/")[1]: x for x in manifest["files"]}
    test_certificate()
    arms, certificates = {}, {}
    for name in cohorts.c294.NAMES:
        baseline = cohorts.arm(args.raw_dir, entries, name, 64)
        require(baseline == prior["arms"][name], "cohort bridge")
        path = f"{name}.native/events.tsv"
        raw = cohorts.verified(args.raw_dir / path, entries[path]["sha256"], entries[path]["bytes"])
        gross, retained, counts = extract(raw, baseline)
        window = baseline["journal_decode32_floor_us"]
        arms[name] = dict(journal_floor_us=window, rank_sha256=baseline["ordered_rank_sha256"],
                          cpu_demands=dict(counts))
        certificates[name] = {}
        for label, groups in (("broad", gross), ("paid", retained)):
            arms[name][label], certificates[name][label] = certificate(groups, 64, window)
    decision = "NO_GO" if all(a["paid"]["six_excluded"] for a in arms.values()) else "INCONCLUSIVE"
    serialized = (json.dumps(certificates, separators=(",", ":")) + "\n").encode()
    report = dict(status=decision, bound="TRACE_DERIVED_CONDITIONAL", fixed_keys=64,
                  protocol_sha256=PROTOCOL, cohort_receipt_sha256=EVIDENCE, arms=arms,
                  certificate_sha256=hashlib.sha256(serialized).hexdigest())
    (args.new_output_dir / "prices.json").write_bytes(serialized)
    tmp = args.new_output_dir / "receipt.pending"
    tmp.write_text(json.dumps(report, indent=2) + "\n")
    tmp.replace(args.new_output_dir / "receipt.json")


if __name__ == "__main__":
    main()
