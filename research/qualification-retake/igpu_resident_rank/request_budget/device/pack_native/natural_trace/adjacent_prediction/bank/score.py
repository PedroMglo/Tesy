"""Charge the intersection of the retained bank and four predicted staged reads."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
AD = run_path(str(HERE.parent / "score.py"))
B = run_path(str(HERE.parents[1] / "tier_budget/first_use/previous_layer/bank/score.py"))
check, checked = AD["check"], AD["checked"]
SIZE, WINDOW = AD["PAYLOAD"], AD["WINDOW"]
RATES = (4_500_000_000, 8_000_000_000)
METHOD = "0612d0462af0e5e8eba6266712d17522144872f0c096af4ff3d16ebec7a4916e"
AD_HASH = "87fd5325baa876734e6406884df1252e3ce6c37e31744549896a651fdd09ae5d"


def charge(target, bank, choices, actual, gap):
    ordered = set(choices)
    hit = target & bank
    pred = (target - bank) & ordered
    check(target <= actual and len(ordered) == len(choices) <= 4 and gap >= 0, "site")
    c = Counter(
        denominator=len(target),
        bank=len(hit),
        extra=len(pred),
        duplicate=len(hit & ordered),
        union=len(hit | pred),
        offers=len(choices),
        unused=len(ordered - actual),
        bank_reissued=len(ordered & bank),
    )
    for rate in RATES:
        ticks, rem = divmod(SIZE * 10**9, rate)
        check(rem == 0, "whole-expert ticks")
        c[f"unbounded_ns_{rate}"] = (len(target) - len(hit | pred)) * ticks
        c[f"residual_ns_{rate}"] = (len(target) - len(hit)) * ticks - min(gap, len(pred) * ticks)
    return c


def run(args):
    method = AD["P"]["TIER"]["sha"]
    check(method(HERE / "protocol.md") == METHOD, "protocol")
    previous = checked(HERE.parent / "receipt.json", AD_HASH)
    check(AD["assess"](args.part63, args.family) == previous, "selection bridge")
    unlimited, windows = B["run"](args)
    sealed = checked(
        B["HERE"] / "receipt.json",
        "ba53f8bf1f863204ee95053e4f35ac50f048455b58071fbdfc024d8215f048ac",
    )
    table = B["HERE"] / "windows.tsv"
    check(method(table) == sealed["windows_sha256"], "sealed windows")
    saved_rows = [tuple(map(int, line.split())) for line in table.read_text().splitlines()[1:]]
    check(
        windows == saved_rows and unlimited | {"windows_sha256": method(table)} == sealed,
        "gap/bank bridge",
    )
    cut = args.part63 / "tesy-policy-natural-physical-20261125-r02/ON"
    first = json.loads((cut / "before-t2.json").read_bytes())
    ordered = checked(cut / "before-t2-candidates.json", unlimited["initial_bank_sha256"])
    bank = set(map(tuple, ordered["capacities"]["353"]["ordered_keys"]))
    hist = AD["READ"](cut / "raw/events.pfj")[0][: first["records"]]
    check(AD["CROSS"]["AUDIT"]["record_digest"](hist) == previous["t1_cut_sha256"], "cut")
    pairs, frequency = AD["train"](hist)
    rows = AD["READ"](args.family / "ON/raw/events.pfj")[0]
    proposals, cuts, routes = AD["select"](rows, pairs, frequency)
    host = AD["P"]["TIER"]["NATIVE"]["host_trace"](rows)
    strict = defaultdict(set)
    for (layer, expert), (call, tile, _, _) in AD["CROSS"]["strict_keys"](rows, host).items():
        if layer < 25:
            strict[call, tile, layer].add(expert)
    gaps = {}
    for call, tile, layer, _, n, h, _, gap in windows:
        key = call, tile, layer
        group = strict[key]
        check(len(group) == n and sum((layer, e) in bank for e in group) == h, "site bridge")
        check(key not in gaps, "duplicate first window")
        gaps[key] = gap
    check(strict.keys() == gaps.keys(), "all positive groups")
    sums = defaultdict(lambda: defaultdict(Counter))
    for key in sorted(routes):
        call, tile, layer = key
        target = strict.get(key, set())
        actual = {e for row in routes[key].values() for e in row}
        retained = {e for bank_layer, e in bank if bank_layer == layer}
        original = proposals.get(key, {})
        merged = {}
        if key in proposals:
            eligible, _ = cuts[key]
            source = routes[call, tile, layer - 1].values()
            merged = AD["choose"](source, layer, pairs, frequency, eligible - retained)
        arms = {
            "none": (set(), []),
            "bank": (retained, []),
            "adjacent": (set(), original.get("adjacent", [])),
            "fixed_union": (retained, original.get("adjacent", [])),
            "joint_adjacent": (retained, merged.get("adjacent", [])),
            "joint_frequency": (retained, merged.get("frequency", [])),
            "joint_oracle": (retained, sorted(target - retained)[:4] if key in proposals else []),
        }
        for label, (active_bank, choices) in arms.items():
            sums[label][call].update(charge(target, active_bank, choices, actual, gaps.get(key, 0)))
    budget = previous["CPU_budget_ns"]
    summary = {}
    for label, calls in sums.items():
        total = calls[1].copy()
        total.update(calls[2])
        check(
            total["denominator"] == 375 and total["bank"] + total["extra"] == total["union"],
            "union conservation",
        )
        total["requested_range_bytes"] = total["offers"] * WINDOW
        total["unused_range_bytes"] = total["unused"] * WINDOW
        for rate in RATES:
            total[f"margin_ns_{rate}"] = budget - total[f"residual_ns_{rate}"]
        summary[label] = {"by_call": calls, "total": total}
    base, combined = summary["adjacent"]["total"], summary["fixed_union"]["total"]
    check(
        base["extra"] == previous["arms"]["adjacent"]["total"]["strict"]
        and combined["extra"] + combined["duplicate"] == base["extra"],
        "same offers",
    )
    check(
        all(
            summary[a]["total"]["bank_reissued"] == 0
            for a in ("joint_frequency", "joint_adjacent", "joint_oracle")
        ),
        "rerank",
    )
    check(sum(1 for key in routes if key[2] > 0) == 144, "all decision sites")
    return {
        "status": "TRACE_DERIVED_JOINT_CAPACITY_AND_DEADLINES",
        "protocol_sha256": METHOD,
        "source_receipts": [AD_HASH, method(B["HERE"] / "receipt.json")],
        "pfj_sha256": previous["pfj_sha256"],
        "CPU_budget_ns": budget,
        "arms": summary,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ("part63", "family", "backend", "new-output-dir"):
        parser.add_argument("--" + k, type=Path, required=True)
    a = parser.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a)
    except Exception as exc:
        (a.new_output_dir / "FAIL.json").write_text(json.dumps({"error": str(exc)}) + "\n")
        raise
    with (a.new_output_dir / "receipt.json").open("x") as out:
        json.dump(result, out, sort_keys=True, indent=2)
        out.write("\n")
