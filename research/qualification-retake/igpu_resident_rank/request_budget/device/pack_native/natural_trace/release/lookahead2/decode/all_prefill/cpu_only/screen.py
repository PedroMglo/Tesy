"""Three fixed release masks on the same C291 transfer and SET budget."""

import argparse
import json
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
A = run_path(str(HERE.parent / "screen.py"))
C, D, L, Q = (A[k] for k in ("C", "D", "L", "Q"))
PHASES = A["PHASES"]
RATE = 4_500_000_000
RULES = "323f51a3a664251b30ac5e627bf7778789085cb17fb847d736e8a4fc153c8401"
PREVIOUS = "ed035fcfa6a98e12ec7bbef29343256caa7c857f942d3ffa689e4bb562974147"
check, canonical = A["check"], A["canonical"]


def cpu(call, layer):
    return call in (1, 2) and 1 <= layer <= 24


def include(choice, jobs, subset):
    return {
        k: src if cpu(jobs[k].site[0], jobs[k].site[2]) == subset else "outside_subset"
        for k, src in choice.items()
    }


def close_price(tasks, total, sets, source):
    values = {p: Counter() for p in PHASES}
    for c in range(1, 49):
        early, net, both = D["resources"](total[c], tasks[c], RATE, sets[c])
        z = values[C["phase"](c)]
        z.update(
            pack_bytes=total[c],
            link_ns=net,
            set_ns=sets[c],
            either_resource_ns=both,
            early_scaled_bytes=early,
        )
    for value in values.values():
        value["early_bytes_floor"] = value.pop("early_scaled_bytes") // A["NS"]
    price = D["budget"](
        source["baseline_first_ns"],
        source["baseline_decode_ns"],
        [source["callback_ns"][p] for p in PHASES],
        [values[p]["either_resource_ns"] for p in PHASES],
    )
    price["independent_first_saving_needed_ns"] = max(0, -price["first_margin_ns"])
    price["independent_decode_saving_needed_ns"] = max(0, -price["decode_margin_ns"])
    if price["independent_first_saving_needed_ns"]:
        allowed = min(
            47 * A["NS"] // 6,
            price["decode_floor_ns"] - price["independent_first_saving_needed_ns"],
        )
        price["minimum_tokens_s_if_only_additional_early_decode_improves"] = (
            47 * A["NS"] / allowed if allowed > 0 else None
        )
    return {"phases": values, "budgets": price}


def merge_parts(left, right, total):
    l_tasks, l_total, work = left
    r_tasks, r_total, other_work = right
    check(work == other_work, "overlapping or missing SET floors")
    for c in range(1, 49):
        check(l_total[c] + r_total[c] == total[c], "lost or duplicated source payload")
    return {c: [*l_tasks[c], *r_tasks[c]] for c in range(1, 49)}


def assess(rows, tiers, bank, source, parent):
    host = C["NATIVE"]["host_trace"](rows)
    jobs, pop, sites = A["jobs"](rows, host, tiers, bank)
    check(
        pop == parent["population"] and sites == parent["reservation_first_use_sha256"],
        "causal jobs",
    )
    choice, store = A["staging"](rows, jobs, bank, tiers, "transient")
    frozen = parent["modes"]["transient"]
    check(all(frozen[k] == v for k, v in store.items()), "same storage")
    check(all((tier == "CPU") == (layer < 25) for layer, tier in tiers.items()), "placement")
    marks = (L["markers"](rows, host), D["decode_markers"](rows, host))
    clocks = [L["contracted"](m[-1]) for m in marks]
    selected_counts = Counter(s for k, s in choice.items() if cpu(jobs[k].site[0], jobs[k].site[2]))
    forecast_rows = sum(len(v) for (c, _, layer), v in marks[0][2].items() if cpu(c, layer))
    check(forecast_rows == 24 * 153, "CPU forecast opportunity")
    answer = {}
    for release in ("ranks_observed", "earliest_outer"):

        def make(scope, width, release=release):
            return A["analyse_placements"](jobs, scope, marks, clocks, release, width)

        own, total, set_cost = make(choice, 0)
        all_plus, tot_full, sets_full = make(choice, 4)
        check(tot_full == total and sets_full == set_cost, "different work")
        plus_cpu = make(include(choice, jobs, True), 4)
        own_other = make(include(choice, jobs, False), 0)
        mixed = merge_parts(plus_cpu, own_other, total)
        modes = {
            name: close_price(tasks, total, set_cost, source)
            for name, tasks in (("own", own), ("prefill_cpu_only", mixed), ("all", all_plus))
        }
        for ph in PHASES[1:]:
            check(
                modes["own"]["phases"][ph] == modes["prefill_cpu_only"]["phases"][ph],
                "decode is not protected",
            )
        for width, mode in ((0, "own"), (4, "all")):
            if width == 0 and release == "earliest_outer":
                continue  # The parent evaluated this control only at the observed local route.
            wanted = frozen["scenarios"][f"{release}/{width}/{RATE}"]["priced_set_margins_ns"]
            b = modes[mode]["budgets"]
            check([b["first_margin_ns"], b["decode_margin_ns"]] == wanted, "frozen anchor")
        for clk in ("first", "decode"):
            field = clk + "_floor_ns"
            a, b, c = (modes[m]["budgets"][field] for m in ("own", "prefill_cpu_only", "all"))
            check(a >= b >= c, "extra release cannot increase the floor")
        answer[release] = modes
    return {
        "eligible_cpu_reservations": selected_counts,
        "projected_rows": forecast_rows,
        "dense_router_MAC": forecast_rows * 2880 * 128,
        "groups": answer,
    }


def run(archive, backend):
    check(
        L["digest"](HERE / "protocol.md") == RULES
        and L["digest"](HERE.parent / "screen.py")
        == "8c7de037b3242e7e8951bcced7a04375aca491ff7a9782923758305493c43370",
        "source",
    )
    prior = A["run"](archive, backend)
    check(D["sha"](canonical(prior)) == PREVIOUS, "complete predecessor")
    source = L["pinned"](HERE.parents[1] / "receipt.json", A["PREVIOUS"])
    refs = C["SOURCES"]
    roots = {k: archive / ("part-" + k[1:]) / v[0] for k, v in refs.items()}
    seal, rows, tiers, _ = Q["read_new"](roots["P106"], refs["P106"][1])
    bank = set(map(tuple, seal["banks"]["prefill"]["ordered_keys"]))
    p106 = assess(rows, tiers, bank, source["P106"], prior["P106"])
    del rows
    _, _, _, audit = C["CHAIN"]["chain"](roots["P97"], refs["P97"][1])
    rows, h = L["T"]["PFJ"]["read_journal"](roots["P97"] / "ON/raw/events.pfj")
    check(h == audit["header"], "sealed P97")
    p97 = assess(rows, tiers, bank, source["P97"], prior["P97"])
    check(p97["eligible_cpu_reservations"] == p106["eligible_cpu_reservations"], "same population")
    return {
        "status": "REPRODUCED_CPU_ONLY_PREFILL_CONDITIONAL_CLOCKS",
        "protocol_sha256": RULES,
        "source_sha256": L["digest"](Path(__file__)),
        "prior_sha256": PREVIOUS,
        "payload_Bps": RATE,
        "P97": p97,
        "P106": p106,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("archive", "backend", "new-output-dir"):
        p.add_argument("--" + k, type=Path, required=True)
    args = p.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(args.archive, args.backend)
    except (ValueError, OSError, KeyError, StopIteration) as ex:
        result = {"status": "FAIL_PRESERVED", "error": type(ex).__name__, "reason": str(ex)}
    (args.new_output_dir / "receipt.json").write_text(
        json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    print(result["status"])
    raise SystemExit(int(result["status"] != "REPRODUCED_CPU_ONLY_PREFILL_CONDITIONAL_CLOCKS"))
