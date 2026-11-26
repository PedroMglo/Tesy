"""Compose pre-POST bank membership and a preceding-layer release at each sealed CPU demand."""

import argparse
import hashlib
import json
from collections import defaultdict
from itertools import accumulate, pairwise
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
PREV = run_path(str(HERE.parent / "score.py"))
LAST = run_path(str(HERE.parents[1] / "last353.py"))
check, checked = LAST["check"], LAST["checked"]
PREV_SHA = "db207a310396e24e86b28766292cffe12b20f3f8ac2cfc637839a7b28da9d600"
LAST_SHA = "c63eb5121c53d2f83fe75bf4532afeb912d306987f982f8b36f79e3c30ee80ce"
PROTOCOL = "c6919977752bf4c3593c1390b6be3ab006dae4529bf414be9d4a47679de7e5e3"
SIZE = PREV["SIZE"]


def cost(jobs, gap, time_per_job, whole):
    if whole:
        return max(0, jobs - gap // time_per_job) * time_per_job
    return max(0, jobs * time_per_job - gap)


def cross(cells, rate, whole, budget):
    ticks, remainder = divmod(SIZE * 10**9, rate)
    check(ticks > 0 and not remainder, "exact complete-payload ticks")
    sums = dict.fromkeys(("neither", "previous", "last353", "combined", "offers_combined"), 0)
    substitutions = []
    for n, hits, offers, gap in cells:
        check(0 <= hits <= offers <= n and gap >= 0, "inconsistent site membership")
        missing = n - hits
        sums["neither"] += n * ticks
        sums["previous"] += cost(n, gap, ticks, whole)
        sums["last353"] += missing * ticks
        sums["combined"] += cost(missing, gap, ticks, whole)
        sums["offers_combined"] += cost(n - offers, gap, ticks, whole)
        local = [cost(missing - i, gap, ticks, whole) for i in range(offers - hits + 1)]
        gains = [a - b for a, b in pairwise(local)]
        check(gains == sorted(gains, reverse=True), "non-concave substitution credit")
        substitutions.extend(gains)
    sums["last353_marginal_after_previous"] = sums["previous"] - sums["combined"]
    sums["previous_marginal_after_last353"] = sums["last353"] - sums["combined"]
    gross_bank = sums["neither"] - sums["last353"]
    sums["overlapping_saving"] = gross_bank - sums["last353_marginal_after_previous"]
    check(sums["overlapping_saving"] >= 0, "negative interaction")
    margins = {k: budget - sums[k] for k in ("combined", "offers_combined")}
    need = max(0, -margins["combined"])
    best = list(accumulate(sorted(substitutions, reverse=True), initial=0))
    check(best[-1] == sums["combined"] - sums["offers_combined"], "oracle total")
    minimum = next((i for i, gain in enumerate(best) if gain >= need), None)
    return {
        "ns": sums,
        "margin_ns": margins,
        "minimum_extra_useful_selections_from_offers": minimum,
        "time_still_missing_even_with_all_offers_ns": max(0, -margins["offers_combined"]),
        "decision": {
            k: "NO_GO_FIXED_SCOPE" if v < 0 else "HEADROOM_ONLY" for k, v in margins.items()
        },
    }


def run(args):
    sha = LAST["P"]["TIER"]["sha"]
    check(sha(HERE / "protocol.md") == PROTOCOL, "protocol")
    previous = checked(HERE.parent / "receipt.json", PREV_SHA)
    last = checked(HERE.parents[1] / "last353.json", LAST_SHA)
    check(LAST["score"](args.part63, args.family) == last, "original prefix and P bindings")
    base, windows = PREV["assess"](args)
    check(
        base | {"windows_sha256": previous["windows_sha256"]} == previous,
        "reopened DATA, route, clock and horizons",
    )
    check(sha(HERE.parent / "windows.tsv") == previous["windows_sha256"], "published horizons")

    arm = args.part63 / "tesy-policy-natural-physical-20261125-r02/ON"
    old = checked(LAST["ENTRY"] / "receipt.json", LAST["ENTRY_SHA"])
    auth = checked(arm / "receipt.json", old["source_seals"]["arm"])
    cut = checked(arm / "before-t2.json", auth["before_t2_sha256"])
    candidate = checked(arm / "before-t2-candidates.json", last["candidate_sha256"])
    bank = set(map(tuple, candidate["capacities"]["353"]["ordered_keys"]))
    read = LAST["P"]["TIER"]["PFJ"]["read_journal"]
    old_rows, h = read(arm / "raw/events.pfj")
    check(h["journal_sha256"] == last["journal_sha256"]["63"], "T1 journal")
    prefix = old_rows[: cut["records"]]
    check(LAST["AUDIT"]["record_digest"](prefix) == last["prefix_sha256"], "T1 cut")
    offers = set(LAST["AUDIT"]["state_before"](prefix)[2])
    check(len(bank) == 353 and bank <= offers, "bank subset")
    rows, h = read(args.family / "ON/raw/events.pfj")
    check(h["journal_sha256"] == last["journal_sha256"]["97"], "T2 journal")
    by_site = defaultdict(set)
    host = LAST["P"]["TIER"]["NATIVE"]["host_trace"](rows)
    for key, site in LAST["strict_keys"](rows, host).items():
        by_site[site].add(key)
    cells, evidence = [], []
    for w in windows:
        site = tuple(w[k] for k in ("call", "tile", "layer", "wave"))
        group = by_site[site]
        check(len(group) == w["jobs"] and w["horizon"] in ("drained", "layer0"), "strict window")
        vals = len(group), len(group & bank), len(group & offers), w["gap_ns"]
        cells.append(vals)
        evidence.append((*site, *vals))
    check(
        len(cells) == 110 and tuple(map(sum, zip(*cells, strict=True)))[0:3] == (375, 65, 236),
        "coverage",
    )
    budget = previous["budget_ns"]
    cases = {}
    for rate, suffix in zip(PREV["RATES"], ("4p5", "8"), strict=True):
        cases[suffix] = {}
        for label, whole in (("partial", False), ("whole", True)):
            result = cross(cells, rate, whole, budget)
            check(
                result["ns"]["previous"] == previous["totals"][f"{label}_residual_ns_{suffix}"],
                "preceding-layer ablation",
            )
            cases[suffix][label] = result
    return {
        "status": "TRACE_DERIVED_WINDOW_BANK_INTERSECTION",
        "verifier_sha256": sha(Path(__file__)),
        "protocol_sha256": PROTOCOL,
        "source_receipts_sha256": {"membership": LAST_SHA, "horizons": PREV_SHA},
        "initial_bank_sha256": last["candidate_sha256"],
        "journals_sha256": last["journal_sha256"],
        "sampled_ids_sha256": previous["sampled_ids_sha256"],
        "route": previous["route"],
        "budget_ns": budget,
        "strict": sum(row[0] for row in cells),
        "bank_hits": sum(row[1] for row in cells),
        "offers_hit": sum(row[2] for row in cells),
        "window_groups": len(cells),
        "rates_Bps": dict(zip(("4p5", "8"), PREV["RATES"], strict=True)),
        "cases": cases,
    }, evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("part63", "family", "backend", "new-output-dir"):
        parser.add_argument("--" + arg, required=True, type=Path)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        result, evidence = run(args)
        lines = ["call\ttile\tlayer\twave\tjobs\tbank_hits\toffers_hit\tgap_ns"]
        lines.extend("\t".join(map(str, r)) for r in evidence)
        data = ("\n".join(lines) + "\n").encode()
        with (args.new_output_dir / "windows.tsv").open("xb") as f:
            f.write(data)
        result["windows_sha256"] = hashlib.sha256(data).hexdigest()
    except Exception as exc:
        result = {"status": "FAIL_PRESERVED", "reason": f"{type(exc).__name__}: {exc}"}
    with (args.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
