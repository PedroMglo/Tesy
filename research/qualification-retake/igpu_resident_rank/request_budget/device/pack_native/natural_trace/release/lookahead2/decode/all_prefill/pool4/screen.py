"""Bound read-through reuse across layer cells with a fully shared four-page pool."""

import argparse
import bisect
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
A = run_path(HERE.parent / "screen.py")
D, L, C, Q, check = (A[k] for k in ("D", "L", "C", "Q", "check"))
RATE = 4_500_000_000
SIZE = A["size"]
METHOD = "a495b55017ccc6aa01d542b256027f7028f58f52df7d390d042f02ba2e680e86"


def retention_intervals(cells):
    previous = {}
    same = 0
    links = []
    for site, keys in enumerate(cells):
        for key in keys:
            if key in previous:
                if previous[key] == site:
                    same += 1
                else:
                    links.append((previous[key], site))
            previous[key] = site
    return sorted(links, key=lambda p: (p[1], p[0])), same, len(previous)


def ceiling(links, free, distinct, capacity):
    # End-time interval scheduling. Using the latest compatible end retains
    # every earlier free lane for intervals with an earlier start.
    ends = [-1] * capacity
    keep = 0
    for start, end in links:
        where = bisect.bisect_right(ends, start)
        if where:
            del ends[where - 1]
            ends.append(end)
            keep += 1
    return free + keep + min(capacity, distinct)


def limits(cells, deficit):
    links, free, distinct = retention_intervals(cells)
    count = sum(map(len, cells))
    check(count == len(links) + free + distinct, "interval population")
    initial = ceiling(links, free, distinct, 4)
    # Rounding up once per removed read covers integer-ns flooring per call.
    price = (SIZE * A["NS"] + RATE - 1) // RATE
    required = (max(0, deficit) + price - 1) // price
    low, high = 0, distinct
    if ceiling(links, free, distinct, high) < required:
        minimum = None
    else:
        while low < high:
            mid = (low + high) // 2
            if ceiling(links, free, distinct, mid) >= required:
                high = mid
            else:
                low = mid + 1
        minimum = low
    return dict(
        reads=count,
        distinct_keys=distinct,
        intercell_intervals=len(links),
        within_cell=free,
        optimistic_hits_four=initial,
        upper_credit_ns=initial * price,
        minimum_hits_for_first_margin=required,
        necessary_pages_relaxed=minimum,
    )


def phase_cells(js, bank, begin, end):
    by_site = {}
    for job in js.values():
        if begin <= job.site[0] <= end and job.key not in bank:
            by_site.setdefault(job.site[:3], []).append(job.key)
    return [by_site[k] for k in sorted(by_site)]


def assess(rows, tiers, bank, parent):
    host = C["NATIVE"]["host_trace"](rows)
    js, _, seal = A["jobs"](rows, host, tiers, bank)
    choice, _ = A["staging"](rows, js, bank, tiers, "transient")
    marks = (L["markers"](rows, host), D["decode_markers"](rows, host))
    shrink = [L["contracted"](m[-1]) for m in marks]
    tasks, total, work = A["analyse_placements"](js, choice, marks, shrink, "ranks_observed", None)
    prev = next(
        x
        for x in parent["choices"]
        if x["bytes_per_s"] == RATE
        and x["release"] == "ranks_observed"
        and x["width"] == "unlimited"
        and x["horizon"] == 1
    )
    base = A["projected"](tasks, total, work, parent, RATE, prev)["priced_set_margins_ns"]
    populations = {
        name: limits(phase_cells(js, bank, 1, end), -base[0] if name == "before_piece" else 0)
        for name, end in (("prefill", 2), ("before_piece", 46), ("whole", 48))
    }
    check(
        populations["prefill"]["reads"] == 966 and populations["whole"]["reads"] == 1981,
        "pack jobs",
    )
    first = base[0] + populations["before_piece"]["upper_credit_ns"]
    return dict(
        reservation_sha256=seal,
        base_first_margin_ns=base[0],
        base_decode_margin_ns=base[1],
        populations=populations,
        upper_first_margin_with_four_ns=first,
        status="NO_GO_FOUR_AT_FIXED_RELEASES" if first < 0 else "INCONCLUSIVE_CAPACITY_BOUND",
    )


def run(a):
    check(
        L["digest"](HERE / "protocol.md") == METHOD
        and L["digest"](HERE.parent / "screen.py")
        == "8c7de037b3242e7e8951bcced7a04375aca491ff7a9782923758305493c43370",
        "frozen analysis",
    )
    check(L["digest"](a.backend / "src/llama-moe-stream.cpp") == A["BACKEND"], "source")
    parent = D["run"](a.archive, a.backend)
    check(D["sha"](A["canonical"](parent)) == A["PREVIOUS"], "previous two-phase result")
    refs = C["SOURCES"]
    roots = {k: a.archive / ("part-" + k[1:]) / v[0] for k, v in refs.items()}
    seal, rows, tiers, _ = Q["read_new"](roots["P106"], refs["P106"][1])
    bank = set(map(tuple, seal["banks"]["prefill"]["ordered_keys"]))
    b = assess(rows, tiers, bank, parent["P106"])
    del rows
    _, _, _, audit = C["CHAIN"]["chain"](roots["P97"], refs["P97"][1])
    rows, header = L["T"]["PFJ"]["read_journal"](roots["P97"] / "ON/raw/events.pfj")
    check(header == audit["header"], "P97 input")
    c = assess(rows, tiers, bank, parent["P97"])
    check(b["reservation_sha256"] == c["reservation_sha256"], "paired generation history")
    return dict(
        status="REPRODUCED_SHARED_POOL_CEILING",
        P97=c,
        P106=b,
        method_sha256=METHOD,
        program_sha256=L["digest"](Path(__file__)),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("archive", "backend", "new-output-dir"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    args.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(args)
    except Exception as e:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}")
    with (args.new_output_dir / "receipt.json").open("xb") as stream:
        stream.write(A["canonical"](result))
    print(result["status"], result.get("reason", ""))
    raise SystemExit(int(result["status"] == "FAIL_PRESERVED"))
