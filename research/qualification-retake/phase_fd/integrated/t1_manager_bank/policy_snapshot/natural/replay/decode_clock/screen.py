"""Conditional same-callback prices of the ON C281 decode, for the sealed replay trajectories."""

import argparse
import json
import math
import os
import resource
import signal
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path
from types import FunctionType

HERE = Path(__file__).resolve().parent
REPLAY = HERE.parent
previous = run_path(REPLAY / "screen.py")
need, sha = previous["require"], previous["sha"]
cost = run_path(REPLAY.parent / "cost.py")
clock = run_path(previous["INT"] / "t1_decode_gate/screen.py")["clock"]
FAMILY = "cb70c934dbbe0f1ca7452904718589b44fa906179208e7f95b0c934808d70a42"
REPLAY_SHA = "494bb5d2e73b4e129b020118e1bcf2110f253b1c2b565b5d110023129516aa54"
PAIR_SHA = "bb6e2b508bf35af6001ccbb5bec655ae3235bf69d1a8d74af84b4382b640b889"
COST_SHA = "19e326bc467aa5c6403a29cb3fc05357706f7d23f33bf598928352b02b00592e"
PAYLOAD = 13219200
PACK = 13221888


def same_function(f, updates):
    return FunctionType(
        f.__code__, f.__globals__ | updates, f.__name__, f.__defaults__, f.__closure__
    )


def capture(groups, args, path, reference):
    """Wrap the unmodified callback, including clones used for restoration."""
    start = groups[0]["site"][0] + 2
    jobs, order = {}, iter(groups)

    class Recorder(previous["Manager"]):
        def callback(self, layer, wave, ranks):
            group = next(order)
            site = group["site"]
            need(site[2:] == (layer, wave), "callback location")
            jobs_new, demands = super().callback(layer, wave, ranks)
            if site[0] >= start:
                need(
                    wave == -1
                    and site[1] == 1
                    and len(ranks) == 4
                    and site not in jobs
                    and all(x[4] == 0 for x in jobs_new),
                    "decode contains preload/parking or duplicate",
                )
                jobs[site] = {e: (s, g) for e, s, g, _, _ in jobs_new}
                need(len(jobs[site]) == len(jobs_new), "duplicated logical job")
            return jobs_new, demands

    clone = same_function(previous["clone"], {"Manager": Recorder})
    trajectory = same_function(previous["trajectory"], {"Manager": Recorder, "clone": clone})
    state, record = trajectory(
        groups, *args, priority=path != "r0", restore=path == "restored", reference=reference
    )
    need(next(order, None) is None and len(jobs) == 46 * 36, "callback coverage")
    return state, record, jobs


def measurements(rows, jobs):
    bounds, records = defaultdict(dict), defaultdict(list)
    start = min(site[0] for site in jobs)
    for r in rows:
        if r.call < start:
            continue
        site = (r.call, r.tile, r.layer, r.wave)
        if r.kind in (9, 19, 20, 23):
            need(r.kind not in bounds[site], "duplicate clock")
            bounds[site][r.kind] = r.ns
        elif r.kind in (11, 12, 13, 15, 16, 17):
            records[(site, r.expert, r.slot, r.gen)].append(r)
    out = {}
    for site, experts in jobs.items():
        begin, be, br, end = (bounds[site][n] for n in (9, 19, 20, 23))
        need(begin <= be <= br <= end, "callback clock")
        by_expert = {}
        for e, (s, g) in experts.items():
            rr = records.pop((site, e, s, g))
            need(
                [r.kind for r in rr] == [11, 12, 13, 15, 16, 15, 16, 15, 16, 17]
                and rr[1].a == 0
                and begin <= rr[0].ns <= rr[1].ns <= rr[2].ns
                and rr[-1].ns <= br
                and len({r.worker for r in rr[2:]}) == 1,
                "same-site worker from demand generation to barrier",
            )
            chain = rr[3:-1]
            need(
                [r.component for r in chain] == [0, 0, 1, 1, 2, 2]
                and all(r.begin <= r.ns for r in chain)
                and rr[2].ns <= chain[0].begin
                and chain[-1].ns <= rr[-1].ns
                and all(p.ns <= q.begin for p, q in zip(chain, chain[1:], strict=False)),
                "serial role intervals",
            )
            read = sum(r.ns - r.begin for r in chain[::2])
            sets = sum(r.ns - r.begin for r in chain[1::2])
            need(read + sets <= end - begin, "worker duration exceeds callback")
            by_expert[e] = (s, g, read, sets)
        out[site] = by_expert
    need(set(bounds) == set(jobs) and not records, "unaccounted service")
    return out


def lower(chains):
    # Each duration is in fifths of a nanosecond. Return twentieths of a nanosecond.
    return max(4 * max(chains, default=0), sum(chains))


def price(jobs, observed, bank, bases, read_scale, strict_slot):
    count = {"cpu": Counter(), "cuda": Counter()}
    floor_n20 = 0
    for site, expert_slots in jobs.items():
        layer = site[2]
        c = count["cpu" if layer < 25 else "cuda"]
        durations = []
        original = observed[site]
        c["r0_only_jobs"] += len(original.keys() - expert_slots.keys())
        for e, (slot, gen) in expert_slots.items():
            c["admissions"] += 1
            c["primary_delivery_bytes"] += PAYLOAD
            covered = e in bank[layer]
            tier = "host_bank" if covered else "disk"
            c[tier + "_jobs"] += 1
            c[tier + "_payload_bytes"] += PAYLOAD
            extent = sum(
                (((off + size * e) % 4096 + size + 4095) // 4096) * 4096
                for off, size in bases[layer]
            )
            if not covered:
                c["disk_gguf_requested_bytes"] += extent
                c["disk_pack_requested_bytes"] += PACK
            if e not in original:
                c["new_jobs"] += 1
                c["new_" + tier + "_jobs"] += 1
                c["new_primary_delivery_bytes"] += PAYLOAD
                durations.append(0)
                continue
            oldslot, oldgen, read, sets = original[e]
            c["common_jobs"] += 1
            c["common_same_slot_jobs"] += oldslot == slot
            c["common_same_binding_and_gen_jobs"] += (oldslot, oldgen) == (slot, gen)
            copy_price = sets if not strict_slot or slot == oldslot else 0
            read_price = 0 if covered else read
            c["charged_gguf_read_at_unit_worker_ns"] += read_price if read_scale else 0
            c["charged_set_worker_ns"] += copy_price
            durations.append(read_scale * read_price + 5 * copy_price)
        floor_n20 += lower(durations)
    counts = {k: dict(v) for k, v in count.items()}
    counts["all"] = dict(count["cpu"] + count["cuda"])
    return floor_n20 // 20, counts


def targets(row, fixed, interior_floor, counters, observed, unpriced):
    total = fixed + interior_floor
    costs = {"native_6_47": 47_000_000_000 // 6 + 1}
    for n in (46, 47):
        rate = row[str(n)]["min_decode_rate_at_4p5_if_gaps_retained"]
        need(rate and rate > 0, "invalid prefill crossing")
        costs["cross_" + str(n)] = math.ceil(n * 1e9 / rate)
    gates = {}
    for k, v in costs.items():
        margin = v - total
        gates[k] = dict(
            budget_ns=v,
            margin_ns=margin,
            ceiling_ns_per_admission=margin / counters["admissions"] if margin >= 0 else None,
            maximum_fraction_of_r0_unpriced_callback_ns=margin / unpriced
            if margin >= 0 and unpriced > 0
            else None,
            classification="HEADROOM_ONLY" if margin >= 0 else "NO_GO_FIXED_PRICES",
        )
    return dict(
        fixed_exterior_ns=fixed,
        inside_lower_ns=interior_floor,
        decode_lower_ns=total,
        maximum_gain_vs_measured_r0_ns=observed - total,
        upper_native_tokens_s=47e9 / total,
        gates=gates,
    )


def calculate(family, pair_file, cost_file):
    replay = cost["pinned"](REPLAY / "evidence/receipt.json", REPLAY_SHA)
    pair = cost["pinned"](pair_file, PAIR_SHA)
    priced = cost["pinned"](cost_file, COST_SHA)
    need(priced["cases"] == cost["calculate"](pair, replay), "historical prefill thresholds")
    rows, slots, words, calls, interval, bank, bases, origins = previous["sources"](family, FAMILY)
    need(all(origins[k] == replay[k] for k in origins), "replay provenance")
    groups, reads, w = previous["segment"](rows)
    need(w == replay["observed"], "R0 work")
    unit = json.loads((family / "ON/receipt.json").read_bytes())
    result = previous["pinned"](
        family / "ON/raw", "T2-result.json", unit["t2_result_sha256"], 2 << 20
    )
    # The reusable clock numbers the T2 calls 1..48; the journal starts during T1.
    shift = groups[0]["site"][0] - 1
    only = [r._replace(call=r.call - shift) for r in rows if r.kind in (1, 2, 9, 23)]
    _, timings = clock(only, json.loads(result.read_bytes()), unit["rows"][1])
    trajectories, ref = {}, None
    for path in ("r0", "carry", "restored"):
        state, report, jobs = capture(
            groups, (reads, slots, words, calls, interval, bank, bases), path, ref
        )
        need(
            report == {k: v for k, v in replay[path].items() if k != "comparison"},
            "replay receipts",
        )
        trajectories[path] = jobs
        if path == "r0":
            ref = state
    obs = measurements(rows, trajectories["r0"])
    empty = [set() for _ in range(36)]
    base_lower, _ = price(trajectories["r0"], obs, empty, bases, 5, False)
    residual = timings["decode_remap_union_ns"] - base_lower
    need(residual >= 0, "measured R0 exceeds callback clock")
    output = {}
    for path, jobs in trajectories.items():
        out = output[path] = {}
        for source, b in (("disk", empty), ("bank", bank)):
            ledger = replay[path]["variants"][source]["decode"]["all"]
            prices = {}
            for mode, scale in (("gguf_1", 5), ("gguf_0p8", 4), ("unidentified_pack", 0)):
                for strict in (False, True):
                    ins, c = price(jobs, obs, b, bases, scale, strict)
                    totals = c["all"]
                    need(
                        totals["admissions"] == ledger["admissions"]
                        and totals.get("host_bank_jobs", 0) == ledger.get("bank_hits", 0)
                        and totals["disk_jobs"] == ledger["disk_jobs"]
                        and totals["disk_pack_requested_bytes"] == ledger["packed_pread_bytes"]
                        and totals["disk_gguf_requested_bytes"] == ledger["gguf_pread_bytes"],
                        "charged jobs and volumes",
                    )
                    row = targets(
                        priced["cases"][path][source],
                        timings["fixed_decode_ns"],
                        ins,
                        totals,
                        timings["predicted_ns"],
                        residual,
                    )
                    prices[mode + ("_same_slot" if strict else "_same_tier")] = row | {"by_tier": c}
            out[source] = prices
    return dict(
        status="REPRODUCED_CONDITIONAL_DECODE_SERVICE",
        clocks=timings,
        r0_unpriced_callback_ns=residual,
        r0_full_service_lower_ns=base_lower,
        results=output,
        family_sha256=FAMILY,
        replay_sha256=REPLAY_SHA,
        cost_sha256=COST_SHA,
        pair_sha256=PAIR_SHA,
        pfj_sha256=origins["pfj_sha256"],
        policy_sha256=origins["policy_sha256"],
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ("family", "pair", "cost", "new-output-dir"):
        ap.add_argument("--" + key, type=Path, required=True)
    a = ap.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        git = [
            "git",
            "--no-optional-locks",
            "-c",
            "core.preloadIndex=false",
            "-c",
            "index.threads=1",
            "-C",
            str(HERE),
        ]
        need(not subprocess.check_output([*git, "status", "--porcelain"]), "dirty checkout")
        resource.setrlimit(resource.RLIMIT_AS, (768 << 20, 768 << 20))
        resource.setrlimit(resource.RLIMIT_CPU, (118, 120))
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("120s wall")))
        signal.alarm(120)
        result = calculate(a.family, a.pair, a.cost) | dict(
            program_sha256=sha(Path(__file__)),
            protocol_sha256=sha(HERE / "protocol.md"),
            commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
            tree=subprocess.check_output([*git, "rev-parse", "HEAD^{tree}"], text=True).strip(),
            manager_sha256=sha(REPLAY / "manager.py"),
            replay_program_sha256=sha(REPLAY / "screen.py"),
            native_clock_program_sha256=sha(previous["INT"] / "t1_decode_gate/screen.py"),
        )
    except Exception as exc:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(exc).__name__}: {exc}")
    finally:
        signal.alarm(0)
    data = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    need(len(data.encode()) < 1 << 20, "result budget")
    with (a.new_output_dir / "receipt.json").open("x") as stream:
        stream.write(data)
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
