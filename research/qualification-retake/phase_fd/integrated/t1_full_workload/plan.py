"""Census and deterministic service sample from one local T2, with no weight reads."""

import argparse
import hashlib
import math
import os
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
METHOD = "7af554164d79a35abdfb7ba18c4fc3bbcfac169cd1f442eca1c2637d20e68861"
OLD = "02961fa8ffd49d4373ea66c57d5c2bf27973b8429b9ac1e0e1128266de63a999"
SEED = "TESY-T1-FULL-WORKLOAD-v1"
EPS = 10**6
POLICIES = ("lru_ram", "evict_backed_first")


def check(ok, reason):
    if not ok:
        raise ValueError(reason)


def region(call, begin, end, first):
    check(begin <= end, "reversed remap")
    if call in (1, 2):
        check(end < first - EPS, "prefill intersects uncalibrated boundary")
        return "call5" if call == 1 else "call148"
    if end < first - EPS:
        return "decode_before"
    if begin > first + EPS:
        return "decode_after"
    return "decode_boundary"


def bucket(paths):
    a, b = paths
    check(
        len(a) == len(b) and all(p in ("disk", "ram", "primary") for seq in paths for p in seq),
        "origin geometry",
    )
    if not a:
        return ("identical", "empty")
    d = b.count("disk") - a.count("disk")
    effect = "fewer" if d < 0 else "more" if d > 0 else "identical" if a == b else "equal_count"
    jobs = max(sum(p != "primary" for p in seq) for seq in paths)
    width = "0" if jobs == 0 else "1" if jobs == 1 else "2-4" if jobs <= 4 else "5+"
    return effect, width


def digest(site):
    s = "|".join([SEED, *map(str, site)])
    return hashlib.sha256(s.encode("ascii")).digest(), site


def remaps(rows):
    open_site = None
    seen = set()
    for r in rows:
        site = (r.call, r.tile, r.layer, r.wave)
        if r.kind == 9:
            check(open_site is None and site not in seen, "duplicate or nested remap")
            open_site = site
            seen.add(site)
            begin, demand = r.ns, []
        elif r.kind == 10:
            check(open_site == site and r.expert not in demand, "unbound demand")
            demand.append(r.expert)
        elif r.kind == 23:
            check(open_site == site and begin <= r.ns, "unbound end")
            yield site, begin, r.ns, demand
            open_site = None
    check(open_site is None, "unfinished remap")


def counts(layer, demand, paths, record, window):
    result = Counter(waves=1, consumers=len(demand))
    for name, seq in zip(POLICIES, paths, strict=True):
        for expert, origin in zip(demand, seq, strict=True):
            result[name + "_" + origin] += 1
            if origin == "disk":
                result[name + "_gguf_fd_bytes"] += sum(
                    x["count"] for x in record(layer, expert)["gguf"]
                )
                result[name + "_pack_fd_bytes"] += window
    return result


def run(args):
    old = run_path(str(PARENT / "t1_primary_layout/plan.py"))
    src, causal = old["src"], old["causal"]
    check(src.sha(HERE / "protocol.md") == METHOD, "protocol")
    previous = src.pinned(PARENT / "t1_primary_layout/plan-receipt.json", OLD)
    oldplan = src.pinned(args.old_plan, previous["plan_sha256"])
    receipt = src.pinned(args.causal_dir / "receipt.json", old["CAUSAL"])
    check(
        receipt["journal_sha256"] == previous["inputs"]["journal"]
        and src.sha(PARENT / "t1_primary_layout/plan.py") == previous["program_sha256"],
        "source lineage",
    )
    prep = src.pinned(
        args.prepared_dir / "receipt.json",
        causal["src"].pinned(
            PARENT / "t1_router_window/evidence/receipt.json", causal["ROUTER_RECEIPT"]
        )["prepare_sha256"],
    )
    check(
        src.sha(args.prepared_dir / "selection.json") == prep["selection_sha256"],
        "prefix before T2",
    )
    x = src.load_inputs(args.part, args.model, args.inventory, args.prepared_dir)
    check(x.journal == receipt["journal_sha256"], "current local session")
    index = src.pinned(args.index, old["INDEX"])
    rb = src.pinned(args.readback, old["READBACK"])
    window = index["weight_window"]
    check(
        rb["status"] == "PASS_FULL_CANONICAL_PACK_READBACK"
        and rb["component_checks"] == 27648
        and index["pack_sha256_write_stream"] == rb["pack_sha256_write_stream"]
        and index["pack_bytes"] == rb["pack_identity"]["size_bytes"]
        and len(index["experts"]) == 4608
        and window == 13221888,
        "C290/C7 authority",
    )
    initial, final, waves = causal["inputs"](x.rows)
    bank = set(map(tuple, x.prefix["capacities"]["353"]["ordered_keys"]))
    check(len(bank) == 353, "causal bank")
    pools = {n: [causal["Pool"](s) for s in initial] for n in POLICIES}
    prices = {n: defaultdict(Counter) for n in POLICIES}
    first = math.ceil(
        math.floor(x.client["request_started_monotonic"] * 1e9)
        + x.client["stream_metrics"]["first_final_content_chunk_s"] * 1e9
    )
    check(
        abs(x.client["stream_metrics"]["first_final_content_chunk_s"] - x.summary["first_final_s"])
        < 1e-6,
        "client marker",
    )
    entries = {}

    def record(layer, e):
        k = layer, e
        if k not in entries:
            entries[k] = old["bind"](layer, e, index, x.meta)
        return entries[k]

    totals, examples = {}, {}
    strata_prev = {tuple(v["site"]): v for v in oldplan["samples"].values()}
    previous_coverage = defaultdict(Counter)
    domains = defaultdict(Counter)
    legacy_cells = {}
    tick = 0
    restored = False
    for site, begin, end, demand in remaps(x.rows):
        call, _, layer, _ = site
        if call > 2 and not restored:
            for n in POLICIES:
                for layer_id, pool in enumerate(pools[n]):
                    pool.restore(layer_id, final[layer_id], bank, tick + 1, prices[n]["restore"])
            restored = True
        paths = [old["origins"](pools[n][layer], layer, demand, bank) for n in POLICIES]
        if demand:
            check(waves[tick] == (call, layer, tuple(demand)), "wave order")
            tick += 1
            for n in POLICIES:
                pools[n][layer].wave(
                    layer,
                    demand,
                    bank,
                    n == POLICIES[1],
                    tick,
                    prices[n]["prefill" if call <= 2 else "decode"],
                )
        domain = region(call, begin, end, first)
        cell = ".".join((domain, "cpu" if layer < 25 else "cuda", *bucket(paths)))
        tally = counts(layer, demand, paths, record, window)
        totals.setdefault(cell, Counter()).update(tally)
        domains[domain].update(tally)
        if site in strata_prev:
            prev = strata_prev[site]
            check(
                demand == prev["demand"] and paths == [prev["paths"][n] for n in POLICIES],
                "old site consumers and sources",
            )
            previous_coverage[domain].update(tally)
            legacy_cells[cell] = legacy_cells.get(cell, 0) + 1
        if domain != "decode_after" and (
            cell not in examples or digest(site) < digest(examples[cell]["site"])
        ):
            examples[cell] = dict(
                site=site,
                demand=demand,
                paths=dict(zip(POLICIES, paths, strict=True)),
                counts=tally,
            )
    check(
        tick == len(waves) and restored and sum(legacy_cells.values()) == len(strata_prev) == 4,
        "coverage",
    )
    for n in POLICIES:
        for when in ("prefill", "restore", "decode"):
            check(
                prices[n][when] == receipt["arms"][n]["restore"][when],
                f"cost conservation {n} {when}",
            )
    for domain_name, denominator in (("call148", "148"), ("decode", "decode")):
        for tier in ("cpu", "cuda"):
            n = sum(
                v["waves"]
                for cell, v in totals.items()
                if cell.startswith(domain_name)
                and cell.split(".")[1] == tier
                and not cell.endswith(".empty")
            )
            check(
                n == previous["tallies"][denominator + "_" + tier]["nonempty_waves"],
                "historic coverage",
            )
    actual = {}
    prices_ = {}
    for cell, example in sorted(examples.items()):
        actual[cell] = dict(
            example, population=totals[cell]["waves"], site_sha256=digest(example["site"])[0].hex()
        )
        prices_[cell] = example["counts"]
    sample_sum = sum(prices_.values(), Counter())
    sample_keys = sorted({(v["site"][2], e) for v in actual.values() for e in v["demand"]})
    plan = dict(
        samples=actual,
        entries=[record(*k) for k in sample_keys],
        weight_window=window,
        journal=x.journal,
        index=old["INDEX"],
        readback=old["READBACK"],
        causal=old["CAUSAL"],
    )
    src.possible.save(args.new_output_dir / "plan.json", plan)
    future = (
        sum(sample_sum[n + s] for n in POLICIES for s in ("_gguf_fd_bytes", "_pack_fd_bytes")) * 5
    )
    counters = [x["counts"] for x in actual.values()]
    max_workers = max(max(t[n + "_disk"] + t[n + "_ram"] for n in POLICIES) for t in counters)
    return dict(
        status="GO_DESIGN_SERVICE_SAMPLE_ONLY",
        journal_sha256=x.journal,
        former_plan_sha256=previous["plan_sha256"],
        plan_sha256=src.sha(args.new_output_dir / "plan.json"),
        source_sha256=src.sha(Path(__file__)),
        protocol_sha256=METHOD,
        cells=totals,
        domain_totals=domains,
        previous_sample_by_domain=previous_coverage,
        previous_sample_by_cell=legacy_cells,
        sample_by_cell=prices_,
        sample_total=sample_sum,
        selected_strata=len(actual),
        selected_distinct_records=len(sample_keys),
        prospective_compact_pack_bytes=len(sample_keys) * window,
        largest_delivery_jobs=max_workers,
        candidate_fd_bytes_per_process_at_five_passes=future,
        restore_by_policy={n: prices[n]["restore"] for n in POLICIES},
        prefill_nonempty_previous=sum(
            r["nonempty_waves"] for k, r in previous["tallies"].items() if k.startswith("148")
        ),
        model_forwards=0,
        observed_service_prices=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for n in (
        "part",
        "model",
        "inventory",
        "prepared-dir",
        "causal-dir",
        "old-plan",
        "index",
        "readback",
        "new-output-dir",
    ):
        p.add_argument("--" + n, type=Path, required=True)
    args = p.parse_args()
    os.umask(0o077)
    args.new_output_dir.mkdir(mode=0o700)
    try:
        report = run(args)
    except Exception as exc:
        report = {"status": "FAIL_PRESERVED", "error": f"{type(exc).__name__}: {exc}"}
    import json

    with (args.new_output_dir / "receipt.json").open("x") as f:
        json.dump(report, f, allow_nan=False, sort_keys=True, indent=2)
        f.write("\n")
    print(report["status"])
    return int(report["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
