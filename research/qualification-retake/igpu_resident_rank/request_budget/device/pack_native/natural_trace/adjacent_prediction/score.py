"""Replay next-layer staging choices using only completed T1 and causal T2 state."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
CROSS = run_path(str(HERE.parent / "tier_budget/first_use/last353.py"))
P = CROSS["P"]
check, checked = P["check"], P["checked"]
READ = P["TIER"]["PFJ"]["read_journal"]
PAYLOAD, WINDOW = P["PAYLOAD"], P["RELEASE"]["WINDOW"]
METHOD = "947d994fc6444d67f8dc83ed1e8fb25aa5e16927d259bb1edf5c48dc350acc5f"
BRIDGE = "c63eb5121c53d2f83fe75bf4532afeb912d306987f982f8b36f79e3c30ee80ce"
MODES = ("adjacent", "frequency", "oracle")


def quartet(r):
    check(0 <= r.a < 2**32, "quad encoding")
    ids = tuple(r.a.to_bytes(4, "little"))
    check(len(set(ids)) == 4 and max(ids) < 128, "quartet range/uniqueness")
    return ids


def train(prefix):
    routes = {}
    for r in prefix:
        if r.kind == 27:
            key = r.call, r.layer
            check(r.tile == 1 and r.b == 0 and key not in routes, "one training row")
            routes[key] = quartet(r)
    pairs, freq = defaultdict(Counter), defaultdict(Counter)
    for call in range(1, 74):
        for layer in range(1, 36):
            target = routes[call, layer]
            freq[layer].update(target)
            for expert in routes[call, layer - 1]:
                pairs[layer, expert].update(target)
    check(len(routes) == 73 * 36, "training population")
    return pairs, freq


def choose(source, layer, pairs, freq, eligible):
    counts = Counter()
    for expert, repeats in Counter(e for row in source for e in row).items():
        for dest, weight in pairs.get((layer, expert), {}).items():
            counts[dest] += repeats * weight
    by_freq = freq.get(layer, {})
    return {
        "adjacent": sorted(eligible, key=lambda e: (-counts[e], -by_freq.get(e, 0), e))[:4],
        "frequency": sorted(eligible, key=lambda e: (-by_freq.get(e, 0), e))[:4],
    }


def select(rows, pairs, freq):
    slots, initial, seen = defaultdict(dict), defaultdict(set), defaultdict(set)
    source_rows, slots_at_cut, proposals = defaultdict(dict), {}, {}
    for r in rows:
        if r.call > 2:
            break
        if r.kind == 5:
            check(r.a == 2 and r.slot not in slots[r.layer], "entry primary READY")
            slots[r.layer][r.slot] = r.expert, r.gen
            initial[r.layer].add(r.expert)
        elif r.kind == 11:
            old, gen = slots[r.layer][r.slot]
            check(old == r.a and gen + 1 == r.gen, "primary victim and generation")
            slots[r.layer][r.slot] = r.expert, r.gen
        elif r.kind == 10:
            seen[r.layer].add(r.expert)
        elif r.kind == 27 and r.layer < 25:
            key = r.call, r.tile, r.layer
            check(r.b not in source_rows[key], "duplicate logical row")
            source_rows[key][r.b] = quartet(r)
        elif r.kind == 23 and r.layer < 24:
            layer = r.layer + 1
            current = {expert for expert, _ in slots[layer].values()}
            check(len(current) == len(initial[layer]) == 40, "destination slots")
            eligible = set(range(128)) - current - initial[layer] - seen[layer]
            key = r.call, r.tile, layer
            source = source_rows[r.call, r.tile, r.layer]
            # Retain the choice at the last real END of the source layer.
            # This does not read even one event of the destination layer.
            proposals[key] = choose(source.values(), layer, pairs, freq, eligible)
            slots_at_cut[key] = (eligible, len(source))
    for (call, tile, layer), (_, observed) in slots_at_cut.items():
        check(
            observed == len(source_rows[call, tile, layer]) and observed in (5, 20, 32),
            "all source rows available at predecessor END",
        )
    check(len(proposals) == 6 * 24, "all six tiles and CPU destinations 1..24")
    return proposals, slots_at_cut, source_rows


def classify(choices, strict, actual):
    predictions = set(choices)
    check(len(choices) == len(predictions) <= 4 and strict <= actual, "labels/duplicates")
    hit = len(predictions & strict)
    other = len((predictions & actual) - strict)
    waste = len(predictions - actual)
    return Counter(offers=len(choices), strict=hit, other_routed=other, unused=waste)


def evaluate(rows, strict, pairs, freq):
    proposals, cuts, routes = select(rows, pairs, freq)
    by_site = defaultdict(set)
    for (layer, expert), (call, tile, actual_layer, wave) in strict.items():
        if layer < 25:
            check(actual_layer == layer and wave in (-1, 0), "first demand site")
            by_site[call, tile, layer].add(expert)
    check(sum(map(len, by_site.values())) == 375, "strict CPU population")
    counts = {mode: defaultdict(Counter) for mode in MODES}
    digests = {mode: hashlib.sha256() for mode in MODES}
    for key, candidates in sorted(proposals.items()):
        call, _, _ = key
        eligible, _ = cuts[key]
        actual = {e for row in routes[key].values() for e in row}
        target = by_site[key]
        check(target <= eligible & actual, "eligible strict key at source cut")
        # The oracle may decline to issue a read. It reveals only the capacity ceiling.
        candidates["oracle"] = sorted(target)[:4]
        for mode, choices in candidates.items():
            counts[mode][call].update(classify(choices, target, actual))
            digests[mode].update(bytes((*key, len(choices), *choices)))
    return counts, {k: v.hexdigest() for k, v in digests.items()}


def report(c, n):
    check(c["offers"] == c["strict"] + c["other_routed"] + c["unused"], "classification")
    return {k: c[k] for k in ("offers", "strict", "other_routed", "unused")} | {
        "denominator": n,
        "requested_range_bytes": c["offers"] * WINDOW,
        "strict_payload_bytes": c["strict"] * PAYLOAD,
        "unused_range_bytes": c["unused"] * WINDOW,
        "missed_strict": n - c["strict"],
    }


def assess(part63, family):
    check(hashlib.sha256((HERE / "protocol.md").read_bytes()).hexdigest() == METHOD, "method")
    bridge = checked(CROSS["HERE"] / "last353.json", BRIDGE)
    check(CROSS["score"](part63, family) == bridge, "original + packed bridge")
    arm = part63 / "tesy-policy-natural-physical-20261125-r02/ON"
    seal = json.loads((arm / "before-t2.json").read_bytes())
    history = READ(arm / "raw/events.pfj")[0][: seal["records"]]
    check(CROSS["AUDIT"]["record_digest"](history) == bridge["prefix_sha256"], "train cut")
    rows = READ(family / "ON/raw/events.pfj")[0]
    strict = CROSS["strict_keys"](rows, P["TIER"]["NATIVE"]["host_trace"](rows))
    first = checked(CROSS["HERE"] / "result.json", CROSS["FIRST_SHA"])
    counts, digests = evaluate(rows, strict, *train(history))
    budget = first["CPU_first_final_budget_ns"]
    arms = {}
    for mode, calls in counts.items():
        check(set(calls) == {1, 2}, "prefill call coverage")
        total = calls[1] + calls[2]
        arms[mode] = {
            str(i): report(c, first["by_tier"]["CPU"][str(i)]["jobs"])
            for i, c in sorted(calls.items())
        }
        combined = report(total, 375)
        for rate, gate in first["volume"].items():
            residue = combined["missed_strict"] * PAYLOAD * 10**9 // int(rate)
            combined[rate] = {
                "extra_keys_needed": max(
                    0, gate["min_jobs_avoided_or_served_earlier"] - total["strict"]
                ),
                "optimistic_residual_ns": residue,
                "margin_to_10s_ns": budget - residue,
                "decision": "NO_GO_FIXED_SCENARIO" if residue > budget else "HEADROOM_ONLY",
            }
        arms[mode]["total"] = combined
    check(
        all(arms[m]["total"]["strict"] <= arms["oracle"]["total"]["strict"] for m in MODES),
        "oracle domination",
    )
    return {
        "status": "TRACE_DERIVED_CAUSAL_CHOICES_SIMULATED_DELIVERY",
        "protocol_sha256": METHOD,
        "bridge_sha256": BRIDGE,
        "t1_cut_sha256": bridge["prefix_sha256"],
        "pfj_sha256": bridge["journal_sha256"],
        "t1_training_rows": 73 * 36,
        "t1_training_positions": [2047, 2119],
        "prediction_sites": 6 * 24,
        "temporary_buffer_bytes": 4 * WINDOW,
        "CPU_budget_ns": budget,
        "selections_sha256": digests,
        "arms": arms,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("part63", "family", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = assess(a.part63, a.family)
    except Exception as exc:
        (a.new_output_dir / "FAIL.json").write_text(json.dumps({"error": str(exc)}) + "\n")
        raise
    with (a.new_output_dir / "receipt.json").open("x") as out:
        json.dump(result, out, sort_keys=True, indent=2)
        out.write("\n")


if __name__ == "__main__":
    main()
