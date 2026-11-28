"""Certify the complete range of common upstream confidence cutoffs with shared staging."""

import argparse
import os
from itertools import groupby
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
P = run_path(HERE / "price.py")
F, S = P["F"], P["S"]
need, sha, load, save, verified = (F[k] for k in ("need", "sha", "load", "save", "verified"))
BASE = HERE / "evidence-20261128-r01"
BASE_SHA = "6da36ea66ea41e8fce694780b854653fadda0d5fdce536e9f20b9880c29c22d5"
WITNESS_SHA = "cf61d2da2a53195bf3469800a81bb768201fe01daa7891aaea64b4e4643de6c4"
METHOD = "66f3527a2c92e64d4feedb0b48441c8c7ed3ad5eafd9a1d0c4e28cb1b35df457"
MAX = 4 * F["PPM"] + 1


def candidates(model, token, layers, memory, at, reference):
    lexical = [
        F["choices"](
            *model.token_scores(token, layer), memory.resident(layer), model.marginal[layer]
        )[0]
        for layer in range(36)
    ]
    pending, out = {}, []
    for layer, fixed in enumerate(lexical):
        target = layer + 2
        if target < 36:
            scores, _ = model.upstream_scores(layers[layer], target)
            held = memory.resident(target)
            ranked = sorted(
                (e for e in scores if e not in held and scores[e] > 0),
                key=lambda e: (-scores[e], e),
            )[:4]
            pending[target] = [(e, scores[e]) for e in ranked]
        jobs = memory.by_site[at, layer]
        cold = sorted(r[5] for r, effect in jobs if effect[1] is None)
        bits = {e: 1 << i for i, e in enumerate(cold)}
        line = [[score, bits.get(e, 0), int(e in fixed)] for e, score in pending.pop(layer, [])]
        ref = reference[layer]
        half = [bit for score, bit, _ in line if score >= 2 * F["PPM"]]
        need(
            [len(fixed), sum(bits.get(e, 0) for e in fixed)] == ref[1]
            and [len(half), sum(half)] == ref[5]
            and sum(item[1] for item in line) == ref[7][1],
            "independent source replay",
        )
        out.append(line)
        for row, effect in jobs:
            memory.apply(row, effect)
    need(not pending, "unconsumed predictions")
    return out


def capture(a):
    train = load(BASE / "train.json")
    model = F["Frequencies"].unpack(verified(a.trained / "model.json.gz", train["table"]))
    w = verified(a.work, F["WORK"])
    physical = verified(a.serial, F["SERIAL"])
    path = a.arm / "observer/events.pfj"
    need(sha(path) == F["JOURNAL"], "full target journal")
    pf = F["PROFILE"]
    cut, end = pf["metadata"](path, True)
    need(cut == train["records"], "sealed prefix")
    rows = pf["iter_rows"](path, cut, end - cut)
    parent = verified(F["CONTROL"], F["CONTROL_SHA"])
    memory = F["Inventory"](verified(S["PATHS"]["transactions"], parent["inputs"]["transactions"]))
    individual = verified(BASE / "witness.json.gz", WITNESS_SHA)
    token = w["target"][0]
    calls = []
    for ordinal, (pos, layers) in enumerate(F["positions"](rows)):
        need(pos == 2044 + ordinal, "input position")
        if pos < len(w["t2"]):
            model.observe(w["t2"][pos], layers)
            continue
        at = len(calls) + 1
        actual = physical["decode"][at - 1]
        need(
            at == actual["at"]
            and token == w["target"][at - 1]
            and all(set(actual["routes"][i]) == set(layers[i]) for i in range(36)),
            "target cut",
        )
        calls.append(candidates(model, token, layers, memory, at, individual["calls"][at - 1]))
        model.observe(token, layers)
        (token,) = actual["ids"]
    need(len(calls) == 46 and token == w["target"][-1], "first through terminal cuts")
    return dict(calls=calls, individual=WITNESS_SHA, protocol=METHOD, program=sha(Path(__file__)))


def events(lines):
    out = []
    for call, layers in enumerate(lines):
        need(len(layers) == 36, "layer count")
        for layer, options in enumerate(layers):
            scores = [score for score, _, _ in options]
            bits = [bit for _, bit, _ in options if bit]
            need(
                len(scores) <= 4
                and scores == sorted(scores, reverse=True)
                and all(0 < s < MAX for s in scores)
                and len(bits) == len(set(bits))
                and all(b in (1, 2, 4, 8) for b in bits)
                and all(d in (0, 1) for _, _, d in options),
                "invalid candidate group",
            )
            out.extend((score, call, layer, bit, dup) for score, bit, dup in options)
    return sorted(out, reverse=True)


def materialize(ref, offers, lexical, threshold):
    # Independent, direct construction used at both optima and the prior fixed cut.
    chosen = [[list(decisions[int(lexical)]) for decisions in call] for call in ref]
    for score, c, layer, bit, dup in offers:
        if score >= threshold and not (lexical and dup):
            chosen[c][layer][0] += 1
            chosen[c][layer][1] |= bit
    return chosen


class Bound:
    def __init__(self, inputs, reference, lexical, rate):
        self.rate = rate
        self.lexical = lexical
        self.jobs, self.front, self.hots = inputs
        self.masks = [[r[int(lexical)][1] for r in call] for call in reference]
        self.issued = [sum(r[int(lexical)][0] for r in call) for call in reference]
        self.useful = [sum(m.bit_count() for m in call) for call in self.masks]
        self.cold = []
        self.residual = {tag: [0] * 46 for tag in self.jobs}
        self.prices = {}
        for c, call in enumerate(self.masks):
            ncold = 0
            for layer, mask in enumerate(call):
                site = c + 1, layer
                group = self.jobs["P97"].get(site, [])
                n = sum(not hit for _, _, _, hit in group)
                ncold += n
                for tag, jobs in self.jobs.items():
                    work = jobs.get(site, [])
                    need(
                        [(e, h) for e, _, _, h in work] == [(e, h) for e, _, _, h in group],
                        "job and bank identity across price journals",
                    )
                    prices = [P["remaining"](work, m, rate)[0] for m in range(1 << n)]
                    self.prices[tag, c, layer] = prices
                    self.residual[tag][c] += prices[mask]
            self.cold.append(ncold)
        need(sum(self.cold) == 788 and sum(self.cold[:44]) == 768, "cold cuts")

    def admit(self, event):
        _, c, layer, bit, duplicate = event
        old = self.masks[c][layer]
        if self.lexical and duplicate:
            need(not bit or old & bit, "wrongly coalesced useful read")
            return
        need(not (bit & old), "unreported duplicate candidate")
        self.issued[c] += 1
        if bit:
            self.useful[c] += 1
            self.masks[c][layer] |= bit
            for tag, remaining in self.residual.items():
                durations = self.prices[tag, c, layer]
                remaining[c] += durations[old | bit] - durations[old]

    def arms(self):
        times = [
            P["extent"]((cold + n - hit) * P["SIZE"], self.rate)
            for cold, n, hit in zip(self.cold, self.issued, self.useful, strict=True)
        ]
        result = []
        for tag, residual in self.residual.items():
            extra = []
            for rep in (0, 1):
                t = [
                    max(r, dev - hot["hot_ns"][rep])
                    for r, dev, hot in zip(residual, times, self.hots, strict=True)
                ]
                extra.append((sum(t[:44]), sum(t)))
            for f in self.front[tag]:
                first_delta, decode_delta = extra[f["repeat"] - 1]
                first = [x + first_delta for x in f["all_hot_first_range_ns"]]
                decode = f["all_hot_decode_ns"] + decode_delta
                result.append(
                    dict(
                        tag=tag,
                        W=f["W"],
                        repeat=f["repeat"],
                        first_ns=first,
                        decode_ns=decode,
                        common_slack_ns=min(10**10 - first[1], P["DECODE_MAX"] - decode),
                    )
                )
        return result

    def counts(self):
        def cut(end):
            issued, useful = sum(self.issued[:end]), sum(self.useful[:end])
            return dict(
                issued=issued,
                useful=useful,
                wrong=issued - useful,
                device_bytes=(sum(self.cold[:end]) + issued - useful) * P["SIZE"],
            )

        return dict(to_first=cut(44), complete=cut(46))


def direct(inputs, chosen, rate):
    jobs, front, hots = inputs
    results = []
    for tag, groups in jobs.items():
        costs = []
        for c, choices in enumerate(chosen, 1):
            residual = volume = 0
            for layer, (n, mask) in enumerate(choices):
                ns, cold = P["remaining"](groups.get((c, layer), []), mask, rate)
                residual += ns
                volume += cold + n - mask.bit_count()
            costs.append(dict(residual_ns=residual, device_bytes=volume * P["SIZE"]))
        results.extend(dict(tag=tag, **P["projected"](costs, f, hots, rate)) for f in front[tag])
    return results


def merge_descending(spans, low, high):
    if spans and spans[-1][0] == high + 1:
        spans[-1][0] = low
    else:
        spans.append([low, high])


def solve(inputs, ref, offers, lexical, rate, individual):
    b = Bound(inputs, ref, lexical, rate)
    blocks = [(s, list(items)) for s, items in groupby(offers, key=lambda x: x[0])]
    spans = {"any": [], "all": []}
    best = {}
    coverage = 0
    for i, (high, same) in enumerate([(MAX, [])] + blocks):
        low = blocks[i][0] + 1 if i < len(blocks) else 0
        need(low <= high, "empty cutoff interval")
        coverage += high - low + 1
        for event in same:
            b.admit(event)
        arms = b.arms()
        margin = {
            "any": max(
                min(10**10 - r["first_ns"][0], P["DECODE_MAX"] - r["decode_ns"]) for r in arms
            ),
            "all": min(r["common_slack_ns"] for r in arms),
        }
        for key, slack in margin.items():
            if slack >= 0:
                merge_descending(spans[key], low, high)
            if key not in best or slack > best[key]["slack_ns"]:
                best[key] = dict(slack_ns=slack, threshold=high, counts=b.counts(), arms=arms)
    need(coverage == MAX + 1, "all integer thresholds")
    for v in best.values():
        exact = direct(inputs, materialize(ref, offers, lexical, v["threshold"]), rate)
        need(exact == v["arms"], "direct verification at optimum")
    checkpoints = [(MAX, "token" if lexical else "off")]
    if not lexical:
        checkpoints.append((2 * F["PPM"], "upstream"))
    for t, name in checkpoints:
        exact = direct(inputs, materialize(ref, offers, lexical, t), rate)
        expected = [
            dict(tag=tag, **r)
            for tag, rs in individual["arms"][str(rate)][name].items()
            for r in rs
        ]

        def key(r):
            return r["tag"], r["W"], r["repeat"]

        need(sorted(exact, key=key) == sorted(expected, key=key), "frozen endpoint")
    return dict(
        breakpoint_intervals=len(blocks) + 1,
        integer_thresholds=coverage,
        best=best,
        feasible={k: list(reversed(v)) for k, v in spans.items()},
        decision="GO_SCHEDULE_ONLY"
        if spans["all"]
        else "INCONCLUSIVE"
        if spans["any"]
        else "NO_GO",
    )


def price(score_path):
    reference = verified(BASE / "witness.json.gz", WITNESS_SHA)["calls"]
    individual = verified(BASE / "receipt.json", BASE_SHA)
    source = load(score_path)
    need(
        source["protocol"] == METHOD
        and source["individual"] == WITNESS_SHA
        and source["program"] == sha(Path(__file__))
        and len(source["calls"]) == 46,
        "scored witness",
    )
    offers = events(source["calls"])
    base = verified(F["CONTROL"], F["CONTROL_SHA"])
    p = {k: verified(v, base["inputs"][k]) for k, v in S["PATHS"].items()}
    memory = F["Inventory"](p["transactions"])
    jobs = {tag: P["groups"](tag, p, memory) for tag in ("P97", "P106")}
    front = {
        tag: [
            r
            for r in p["resident"]["prices"]
            if r["role"] == "S" and r["replay"] == 1 and r["prefill"] == tag
        ]
        for tag in jobs
    }
    inputs = jobs, front, p["resident"]["evidence"]["arms"]["S"]
    result = {
        str(rate): {
            name: solve(inputs, reference, offers, lex, rate, individual)
            for name, lex in (("upstream", False), ("joint", True))
        }
        for rate in P["RATES"]
    }
    return dict(
        evidence="TRACE_DERIVED_EXISTENCE_FAVORABLE_COSTS",
        result=result,
        protocol=METHOD,
        scores=sha(score_path),
        program=sha(Path(__file__)),
        individual=BASE_SHA,
        model_forwards=0,
    )


def cli():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    ob = sub.add_parser("capture")
    for k in ("trained", "arm", "serial", "work", "new-output-dir"):
        ob.add_argument("--" + k, required=True, type=Path)
    evaluate = sub.add_parser("price")
    evaluate.add_argument("--scores", required=True, type=Path)
    g = evaluate.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", type=Path)
    g.add_argument("--new-output-dir", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    dest = a.new_output_dir
    if dest:
        dest.mkdir()
    try:
        need(sha(HERE / "joint-protocol.md") == METHOD, "joint protocol drift")
        if a.action == "capture":
            save(dest / "scores.json.gz", capture(a))
        else:
            result = price(a.scores)
            if dest:
                save(dest / "receipt.json", result)
            else:
                need(result == load(a.check), "frontier changed")
            print(
                {
                    k: {name: r["decision"] for name, r in v.items()}
                    for k, v in result["result"].items()
                }
            )
    except Exception as exc:
        if dest:
            save(dest / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise


if __name__ == "__main__":
    cli()
