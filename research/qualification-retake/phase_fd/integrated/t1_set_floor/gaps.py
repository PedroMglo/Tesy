"""Fraction of local serial worker gaps admissible at each of the two NVMe prices."""

import argparse
import collections
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
sp = importlib.util.spec_from_file_location("conditional_nvme", HERE / "nvme.py")
nvme = importlib.util.module_from_spec(sp)
sp.loader.exec_module(nvme)
base, src, need = nvme.base, nvme.src, nvme.need
METHOD = "476d64dc18b2bbf8754486b47bfaf5e059be608f520022137929f130cece1b98"
OLD = "210d3bb2eeb8ae907f83320755d09474ae55059450a2261db95fe447a4128bce"
SCALE = 10_000
NAMES = (
    "dispatch_to_first_read",
    "read1_to_set1",
    "set1_to_read2",
    "read2_to_set2",
    "set2_to_read3",
    "read3_to_set3",
    "last_set_to_publish",
)


def chain(records):
    need(
        [r.kind for r in records] == [13, 15, 16, 15, 16, 15, 16, 17],
        "dispatch/three pairs/publication",
    )
    d, *ops, p = records
    need(
        0 <= d.worker < 4
        and len(
            {(r.worker, r.call, r.tile, r.layer, r.wave, r.expert, r.slot, r.gen) for r in records}
        )
        == 1,
        "same worker, site and generation",
    )
    need(
        len({r.component for r in ops[::2]}) == 3
        and all(x.component == y.component for x, y in zip(ops[::2], ops[1::2], strict=True)),
        "read/set roles",
    )
    parts = [
        ops[0].begin - d.ns,
        *(y.begin - x.ns for x, y in zip(ops, ops[1:], strict=False)),
        p.ns - ops[-1].ns,
    ]
    read = sum(r.ns - r.begin for r in ops[::2])
    copies = sum(r.ns - r.begin for r in ops[1::2])
    need(
        all(r.ns >= r.begin > 0 for r in ops)
        and min(parts) >= 0
        and sum(parts) + read + copies == p.ns - d.ns,
        "worker interval partition",
    )
    return parts, read, copies


def observed(rows, start, first, local_groups):
    begin, end, demand, queues, origin, service = (
        {},
        {},
        set(),
        {},
        {},
        collections.defaultdict(list),
    )
    before = collections.defaultdict(int)
    for r in rows:
        key = (r.layer, r.expert, r.slot, r.gen)
        site = (r.call, r.tile, r.layer, r.wave)
        if r.kind == 9:
            begin[site] = r.ns
        elif r.kind == 23:
            end[site] = r.ns
        elif r.kind == 10:
            demand.add((site, key))
        elif r.kind == 11:
            origin[key] = site
        elif r.kind == 12:
            queues.setdefault(key, (site, r.a))
        elif r.kind in (13, 15, 16, 17):
            service[key].append(r)
            if r.kind == 13:
                need(r.ns >= before[r.worker], "overlapping jobs on one worker")
            elif r.kind == 17:
                before[r.worker] = r.ns
    groups = collections.defaultdict(list)
    totals = collections.defaultdict(collections.Counter)
    for key, site in origin.items():
        if not (
            queues[key] == (site, 0)
            and (site, key) in demand
            and begin[site] >= start + base.CALLBACK_MARGIN
            and end[site] <= first - base.CALLBACK_MARGIN
        ):
            continue
        events = service[key]
        parts, r, s = chain(events)
        need(begin[site] <= events[0].ns <= events[-1].ns <= end[site], "worker within callback")
        groups[site].append((key[:2], r, s, sum(parts)))
        tier = "cpu" if key[0] < 25 else "cuda"
        phase = "prefill" if site[0] <= 2 else "decode"
        totals[phase + "_" + tier].update(dict(zip(NAMES, parts, strict=True)))
    extracted = []
    for vals, expected in zip(sorted(groups, key=begin.__getitem__), local_groups, strict=True):
        vals = groups[vals]
        need(
            [(k, r, s) for k, r, s, _ in vals] == [(j.key, j.read, j.copies) for j in expected],
            "qualified worker identities/prices",
        )
        extracted.append([v[3] for v in vals])
    return extracted, dict(totals)


def feasible_grid(evaluate, resolution):
    zero, full = evaluate(0), evaluate(resolution)
    out = dict(zero=zero, full=full, resolution=resolution)
    if not zero["time_fits"]:
        return dict(**out, status="NO_FEASIBLE_FRACTION", maximum_units=None)
    if full["time_fits"]:
        return dict(**out, status="FULL_PRICE_FITS_TIME", maximum_units=resolution)
    low, high = 0, resolution
    while high - low > 1:
        mid = (low + high) // 2
        if evaluate(mid)["time_fits"]:
            low = mid
        else:
            high = mid
    last = evaluate(low)
    after = evaluate(high)
    need(last["time_fits"] and not after["time_fits"] and high == low + 1, "grid cert")
    return dict(
        **out,
        status="BOUNDED_BETWEEN_ADJACENT_FRACTIONS",
        maximum_units=low,
        last=last,
        first_over=after,
    )


def graded(gaps, relevant, eligible, volume, budgets, fixed, capacity=353):
    cache = {}

    def evaluate(n):
        if n in cache:
            return cache[n]
        priced = [
            [
                j._replace(read=SCALE * j.read, copies=SCALE * j.copies + n * g)
                for j, g in zip(jobs, gvals, strict=True)
            ]
            for jobs, gvals in zip(relevant, gaps, strict=True)
        ]
        dp, back = base.solve(priced, eligible, 1, 1)
        k = min(capacity, len(dp) - 1)
        selection = back(k)
        selection.update(
            sorted(eligible - selection, key=lambda key: (key not in volume, key))[: capacity - k]
        )
        need(
            len(selection) == min(capacity, len(eligible))
            and dp[k] == sum(base.bounds(g, selection, 1, 1) for g in priced),
            "reprice witness",
        )
        den = 4 * SCALE
        num = fixed * den + dp[k]
        vol = len(volume - selection) * src.possible.warm.PAYLOAD
        row = dict(
            units=n,
            first_floor_ns=num // den,
            first_floor_numerator=num,
            first_floor_denominator=den,
            remaining_ns=(10**10 * den - num) // den,
            time_fits=num <= 10**10 * den,
            volume_floor_bytes=vol,
            volume_fits={label: vol <= cap for label, cap in budgets.items()},
            selected_sha256=src.audit.digest(sorted(selection)),
        )
        cache[n] = row
        return row

    return feasible_grid(evaluate, SCALE)


def run(a):
    need(base.sha(HERE / "gaps-protocol.md") == METHOD, "gap protocol")
    ref = src.pinned(HERE / "evidence/nvme.json", OLD)
    need(
        ref["program_sha256"] == base.sha(HERE / "nvme.py")
        and ref["protocol_sha256"] == nvme.METHOD,
        "NVMe method identity",
    )
    replay = nvme.run(a)
    need(
        replay == {k: v for k, v in ref.items() if k not in ("program_sha256", "protocol_sha256")},
        "two physical controls",
    )
    ins = src.load_inputs(a.part, a.model, a.inventory, a.prepared_dir)
    start = int(ins.client["request_started_monotonic"] * 10**9)
    first = start + int(ins.client["stream_metrics"]["first_final_content_chunk_s"] * 10**9)
    local, _ = src.admit.t2.planner.assemble(ins.rows, ins.meta, start, first)
    jobs, counts = base.extract(ins.rows, local, ins.meta, start, first)
    intervals, stats = observed(ins.rows, start, first, jobs)
    need(
        len(intervals) == 937 and sum(map(len, intervals)) == 1894 and len(stats) == 4,
        "window scope",
    )
    val = sum(amt for group in intervals for amt in group)
    need(sum(sum(s.values()) for s in stats.values()) == val, "gap accounting")
    eligible = set(map(tuple, ins.available["evicted_ready"]))
    volume = src.admit.t2.eligible_sets(ins.rows)["victims"]
    out = {}
    for i, arm in replay["physical_arms"].items():
        log = a.nvme_part / f"pfj-first-nvme-20261125-r0{i}/raw/groups.jsonl"
        need(base.sha(log) == arm["groups_sha256"], "physical log digest")
        prices, control = nvme.price_log(
            local, [json.loads(line) for line in log.read_bytes().splitlines()]
        )
        need(control == arm["controls"], "prior per-job prices")
        priced = [[j._replace(read=prices[j.key]) if j.first else j for j in g] for g in jobs]
        current = graded(
            intervals,
            priced,
            eligible,
            volume,
            replay["volume_budget_bytes"],
            replay["local_fixed_ns"],
        )
        zero = current["zero"]
        baseline = next(r for r in arm["rows"] if r["capacity"] == 353)
        need(
            zero["first_floor_ns"] == baseline["first_floor_ns"]
            and zero["selected_sha256"] == baseline["selection_sha256"],
            "zero overhead control",
        )
        out[i] = current
    return dict(
        status="PASS_SERIAL_WORKER_GAP_PRICE_DIAGNOSTIC",
        prior_nvme_sha256=OLD,
        journal_sha256=ins.journal,
        capacity=353,
        eligible_t1=len(eligible),
        reserved_in_window=counts["counts"]["included"],
        groups=len(jobs),
        total_gap_worker_ns=val,
        gap_worker_ns_by_phase_tier=stats,
        decision_by_external_price=out,
        fixed_local_ns=replay["local_fixed_ns"],
        defensible_positive_minimum_fraction=None,
        new_ram_copy_required=False,
        physical_forwards=0,
        capture_status="FAIL_PRESERVED",
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in (
        "part",
        "nvme-part",
        "model",
        "inventory",
        "prepared-dir",
        "score-dir",
        "new-output-dir",
    ):
        p.add_argument("--" + key, type=Path, required=True)
    p.add_argument("--copy", choices=(1, 2), type=int, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a)
    except (ValueError, KeyError, IndexError, TypeError, OSError) as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    result.update(program_sha256=base.sha(Path(__file__)), protocol_sha256=METHOD)
    src.possible.save(a.new_output_dir / "receipt.json", result)
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
