"""Price a sealed forecast witness with the same resident, device and client clocks as control."""

import argparse
import os
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
F = run_path(HERE / "forecast.py")
S, MODES = F["SERVICE"], F["MODES"]
need, sha, load, save, verified = (F[k] for k in ("need", "sha", "load", "save", "verified"))
RATES = (4_500_000_000, 8_000_000_000)
SIZE = S["ALIGNED"]
DECODE_MAX = 47 * 10**9 // 6


def extent(byte_count, rate):
    return (byte_count * 10**9 + rate - 1) // rate


def groups(tag, p, memory):
    prices = {}
    for call, _, layer, *_, work in p["service"]["journals"][tag]["groups"]:
        if call < 3:
            continue
        site = call - 2, layer
        tx = memory.by_site[site]
        sources = {row[5]: effect[1] is not None for row, effect in tx}
        need(site not in prices and sources.keys() == {e for e, _, _ in work}, "price lineage")
        prices[site] = sorted((e, rd, st, sources[e]) for e, rd, st in work)
    need(set(prices) == {site for site, jobs in memory.by_site.items() if jobs}, "price coverage")
    return prices


def remaining(jobs, mask, rate):
    """Mask references cold experts in ascending ID order within this visit."""
    cold_index = 0
    residual = []
    for _, read_ns, copy_ns, bank_hit in jobs:
        predicted = False
        if not bank_hit:
            predicted = bool(mask & (1 << cold_index))
            cold_index += 1
        residual.append((read_ns, copy_ns, predicted or bank_hit))
    need(0 <= mask < 1 << cold_index, "forecast outside the cold set")
    cost = S["price_group"](residual, rate, S["PPM"]) if residual else 0
    return cost, cold_index


def cost_step(layers, prices, at, mode_ix, rate):
    c = Counter()
    for layer, decisions in enumerate(layers):
        name = MODES[mode_ix]
        issued, mask = decisions[mode_ix]
        need(len(decisions) == len(MODES) and mask >= 0, "decision width or mask")
        useful = mask.bit_count()
        need(0 <= useful <= issued <= 4, "one quartet per consumer")
        need(not name.endswith("_free") or issued == useful, "error charged to oracle")
        jobs = prices.get((at, layer), [])
        time, cold = remaining(jobs, mask, rate)
        c.update(residual_ns=time, loads=len(jobs), cold=cold, useful=useful, issued=issued)
    c["wrong"] = c["issued"] - c["useful"]
    c["device_bytes"] = SIZE * (c["cold"] + c["wrong"])
    return c


def projected(rows, front, hots, rate):
    repeat = front["repeat"] - 1
    extra = []
    for call, stats in enumerate(rows):
        hot = hots[call]["hot_ns"][repeat]
        # Both terms are within this one drained call. This grants full overlap of its device work.
        floor = max(hot + stats["residual_ns"], extent(stats["device_bytes"], rate))
        extra.append(floor - hot)
    first = [n + sum(extra[:44]) for n in front["all_hot_first_range_ns"]]
    decode = front["all_hot_decode_ns"] + sum(extra)
    return dict(
        W=front["W"],
        repeat=front["repeat"],
        first_ns=first,
        decode_ns=decode,
        common_slack_ns=min(10**10 - first[1], DECODE_MAX - decode),
    )


def decision(rows):
    if all(r["common_slack_ns"] >= 0 for r in rows):
        return "GO_SCHEDULE_ONLY"
    if any(r["first_ns"][0] <= 10**10 and r["decode_ns"] <= DECODE_MAX for r in rows):
        return "INCONCLUSIVE"
    return "NO_GO"


def phase_counts(rows):
    def summary(seq):
        c = sum(seq, Counter())
        return {k: c[k] for k in ("loads", "cold", "issued", "useful", "wrong", "device_bytes")}

    return {"to_first": summary(rows[:44]), "tail": summary(rows[44:]), "complete": summary(rows)}


def validate_witness(w):
    need(w["modes"] == list(MODES) and len(w["calls"]) == 46, "witness schedule")
    for call in w["calls"]:
        need(len(call) == 36, "one forecast visit per target layer")
        for layer, rows in enumerate(call):
            off, tok, marginal, top, sup, up, other, loose = rows
            need(off == [0, 0] and tok[0] == marginal[0] and up[0] == other[0], "ablation volume")
            need(
                tok[1] & ~top[1] == top[1] & ~sup[1] == up[1] & ~loose[1] == 0,
                "inconsistent nested candidate sets",
            )
            need(layer >= 2 or up == other == loose == [0, 0], "upstream router unavailable")


def run(witness):
    w = load(witness)
    validate_witness(w)
    need(
        w["train"]["prefix"] == F["PREFIX"]
        and w["train"]["program"] == sha(HERE / "forecast.py")
        and w["train"]["protocol"] == F["PROTOCOL"]
        and w["train"]["ranks"] == 74278
        and w["train"]["positions"] == 2120
        and w["t2_prefill_ranks"] == 153 * 35 + 1,
        "training provenance",
    )
    need(
        w["protocol"] == F["PROTOCOL"] == sha(HERE / "protocol.md")
        and w["service"] == F["CONTROL_SHA"]
        and w["work"] == F["WORK"]
        and w["serial"] == F["SERIAL"]
        and w["journal"] == F["JOURNAL"],
        "witness pedigree",
    )
    base = verified(F["CONTROL"], F["CONTROL_SHA"])
    p = {k: verified(path, base["inputs"][k]) for k, path in S["PATHS"].items()}
    memory = F["Inventory"](p["transactions"])
    counts, result = {}, defaultdict(dict)
    for tag in ("P97", "P106"):
        prices = groups(tag, p, memory)
        front = [
            r
            for r in p["resident"]["prices"]
            if r["role"] == "S" and r["replay"] == 1 and r["prefill"] == tag
        ]
        need(len(front) == 4, "independent W and repeats")
        for rate in RATES:
            for mode_ix, name in enumerate(MODES):
                rows = [
                    cost_step(layers, prices, at, mode_ix, rate)
                    for at, layers in enumerate(w["calls"], 1)
                ]
                n = phase_counts(rows)
                need(counts.setdefault(name, n) == n, "different route, selection or bank")
                arms = [
                    projected(rows, f, p["resident"]["evidence"]["arms"]["S"], rate) for f in front
                ]
                if name == "off":
                    control = base["arms"][tag]["prices"]["secondary"][str(rate)]["arms"]
                    for a, b in zip(arms, control, strict=True):
                        need(
                            all(a[k] == b[k] for k in ("W", "repeat", "first_ns", "decode_ns"))
                            and a["common_slack_ns"] == b["common_extra_ns"],
                            "parent clock reconstruction",
                        )
                result[str(rate)].setdefault(name, {})[tag] = arms
    verdicts = {
        rate: {name: decision(tags["P97"] + tags["P106"]) for name, tags in modes.items()}
        for rate, modes in result.items()
    }
    return dict(
        evidence="TRACE_DERIVED_FAVORABLE_RESIDUAL_AND_DEVICE_BOUNDS",
        witness=sha(witness),
        program=sha(Path(__file__)),
        protocol=F["PROTOCOL"],
        control=F["CONTROL_SHA"],
        counts=counts,
        verdicts=verdicts,
        arms=result,
        model_forwards=0,
    )


def cli():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--witness", required=True, type=Path)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--new-output-dir", type=Path)
    g.add_argument("--check", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    if a.new_output_dir:
        a.new_output_dir.mkdir()
    try:
        receipt = run(a.witness)
        if a.check:
            need(receipt == load(a.check), "forecast prices changed")
        else:
            save(a.new_output_dir / "receipt.json", receipt)
        print(receipt["verdicts"])
    except Exception as exc:
        if a.new_output_dir:
            save(a.new_output_dir / "failure.json", dict(status="FAIL_PRESERVED", reason=str(exc)))
        raise


if __name__ == "__main__":
    cli()
