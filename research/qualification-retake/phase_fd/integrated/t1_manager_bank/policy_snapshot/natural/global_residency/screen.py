"""Fixed-initial physical CPU residency with exact target waves and unchanged CUDA service."""

import argparse
import heapq
import json
import os
import resource
import signal
import subprocess
from collections import Counter, defaultdict, deque
from fractions import Fraction
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
NATURAL = HERE.parent
FRONT = NATURAL / "prefill_frontier"
REPLAY = NATURAL / "replay"
front = run_path(FRONT / "screen.py")
check, pinned, sha = (front[k] for k in ("check", "pinned", "digest"))
PAY = 13_219_200
STRIDE = 13_221_888
NS = 10**9
CUT = "991fb5d4804b207e96e190101a0a0d68cad3a46cc1abb766fee47567fab39e9b"
JOINT = "78a53e6d93fed1ad9a9236d74b60b234546d32041f5e572998240b243b82fb7e"
PF_PLAN = "f54b60d5389d4ff503c978e9eed6065e87e0c08a3a245de17d1f59f58e3a152f"
DC_PLAN = "aed09397a16ed706365d73e0d2535427528476b41d66e3d5e43ad90da345d79a"
SEALS = {
    63: front["SEALS"]["archive63"],
    65: "1713b1e73b8e59c34b1f12fc268a9d6caafba09d5c82707476ec9a0febd0069b",
    66: front["SEALS"]["archive66"],
    69: "019d46de75a0742e1704001aed05b124c37eb53151a8083413b3b2cb8ab3a89d",
    71: "6e6b4ca1bd6f41477f8928c7cab6b72432cf3c47d923ede8be20e71231f05646",
}


def schedule(waves, capacity, initial, free):
    """One minimum-paid witness. Every key in a wave is pinned before any victim is chosen."""
    check(capacity > 0 and len(initial) <= capacity, "infeasible physical entry")
    uses = defaultdict(deque)
    for i, pins in enumerate(waves):
        check(len(pins) <= capacity and len(set(pins)) == len(pins), "infeasible wave")
        for key in pins:
            uses[key].append(i)
    resident = set(initial)
    events = []
    for i, pins in enumerate(waves):
        for k in pins:
            check(uses[k].popleft() == i, "use order")
        missing = [k for k in pins if k not in resident]
        remove = max(0, len(resident) + len(missing) - capacity)
        if remove:

            def order(k):
                future = uses[k]
                return (not future, k in free, future[0] if future else 0, k)

            evict = heapq.nlargest(remove, resident.difference(pins), key=order)
            check(len(evict) == remove, "all available backing pinned")
            resident.difference_update(evict)
        resident.update(missing)
        check(len(resident) <= capacity, "capacity overflow")
        events.append(
            (tuple(k for k in missing if k not in free), tuple(k for k in missing if k in free))
        )
    return events, resident


def solve(groups, initial, free, capacity, partitioned, terminal=None):
    # Keep the global group index for the clock even when solving independent layers.
    queues = defaultdict(list)
    events = [((), ()) for _ in groups]
    for i, g in enumerate(groups):
        if g["site"][2] < 25:
            queues[g["site"][2] if partitioned else 0].append((i, g["pins"]))
    repair = Counter()
    for key, rows in queues.items():

        def select(items, pool=key):
            return {k for k in items if not partitioned or k // 128 == pool}

        start = select(initial)
        demands = [pins for _, pins in rows]
        if terminal is not None:
            demands.append(sorted(select(terminal)))
        logs, final = schedule(demands, capacity, start, free)
        for (i, _), event in zip(rows, logs[: len(rows)], strict=True):
            events[i] = event
        if terminal is not None:
            check(select(terminal) <= final, "terminal lost")
            repair.update(disk=len(logs[-1][0]), bank=len(logs[-1][1]))
    return events, repair


def inputs(archive):
    joint = pinned(FRONT / "transport/joint/receipt.json", JOINT)
    fixed = pinned(FRONT / "evidence/receipt.json", joint["frontier_sha256"])
    cut = pinned(FRONT / "oracle/evidence/receipt.json", CUT)
    decode = pinned(
        REPLAY / "decode_clock/transport/service-evidence.json", fixed["origins"]["service"]
    )
    checks = {
        n: pinned(archive / f"part-{n}" / "manifest.json", h)["files"] for n, h in SEALS.items()
    }

    def read(n, path, h):
        check(checks[n][path]["sha256"] == h, "archived " + path)
        return pinned(archive / f"part-{n}" / path, h)

    pf = read(69, "tesy-prefill-transport-plan-20261125-r01/plan.json", PF_PLAN)
    dc = read(65, "tesy-decode-transport-prepare-20261125-r01/plan.json", DC_PLAN)
    hist = read(
        63, "tesy-policy-natural-replay-20261125-r02/receipt.json", fixed["origins"]["replay"]
    )
    check(
        joint["plan_sha256"] == PF_PLAN
        and decode["plan_sha256"] == DC_PLAN
        and fixed["origins"]["journal"] == pf["journal_sha256"]
        and pf["causal_slot_stream_sha256"]
        == dc["causal_slot_stream_sha256"]
        == hist["carry"]["inferred_slot_stream_sha256"],
        "transport origin",
    )
    replay = run_path(REPLAY / "screen.py")
    rows, slots, words, calls, interval, tags, bases, origin = replay["sources"](
        archive / "part-63" / front["FAMILY_NAME"], fixed["origins"]["family"]
    )
    check(all(hist[k] == v for k, v in origin.items()), "T1 origin")
    groups, return_bytes, work = replay["segment"](rows)
    _, r0 = replay["trajectory"](
        groups,
        return_bytes,
        slots,
        words,
        calls,
        interval,
        tags,
        bases,
        priority=False,
        restore=False,
        reference=None,
    )
    check(r0 == hist["r0"] and work == hist["observed"], "R0 observer")
    manager = replay["Manager"](slots, words, calls, interval, tags)
    pri = {i // 40 * 128 + s[0] for i, s in enumerate(slots[:1000]) if s[0] >= 0}
    bank = {owner * 128 + e for owner, keys in enumerate(tags[:25]) for e in keys}
    check(
        len(pri) == 1000 and len(bank) == 263 and sum(map(len, tags[25:])) == 90,
        "physical allocation",
    )
    actual = []
    start = groups[0]["site"][0]
    ranks = terminal = None
    for g, pg in zip(groups, pf["groups"] + dc["groups"], strict=True):
        site = g["site"]
        call, tile, layer, wave = site
        check(site == tuple(pg[k] for k in ("call", "tile", "layer", "wave")), "scope")
        if call == start + 2 and terminal is None:
            members = [sorted(p.ids) for p in manager.pools]
            fingerprint = run_path(FRONT / "oracle/screen.py")["fingerprint"]
            check(
                fingerprint(members) == cut["arms"]["carry"]["resident_set_sha256"][-1],
                "certified first decode members",
            )
            terminal = {owner * 128 + e for owner, ids in enumerate(members[:25]) for e in ids}
        if wave in (-1, 0):
            ranks = g["ranks"]
        allocated, demands = manager.callback(layer, wave, ranks)
        ref = pg["jobs"]
        check(
            [(e, s, gen, "bank" if e in tags[layer] else "disk") for e, s, gen, _, _ in allocated]
            == [(j["expert"], j["slot"], j["generation"], j["source"]) for j in ref],
            "reference allocations",
        )
        if call < start + 2:
            check(
                ranks == pg["ranks"]
                and [(r, old) for _, _, _, old, r in allocated]
                == [(j["source_enqueue"], j["victim"]) for j in ref],
                "prefill route and victim",
            )
        check([e for e, _, _ in demands] == [e for e, _, _ in g["demands"]], "target demand")
        actual.append(
            dict(
                site=site,
                pins=[layer * 128 + e for e, _, _ in demands],
                new_demand={layer * 128 + e for e, _, _, _, r in allocated if r == 0},
                logical_disk={layer * 128 + j["expert"] for j in ref if j["source"] == "disk"},
                logical_bank=sum(j["source"] == "bank" for j in ref),
                phase="call5" if call == start else "call148" if call == start + 1 else "decode",
            )
        )
    check(
        manager.emitted.hexdigest() == dc["causal_slot_stream_sha256"]
        and len(terminal) == 1000
        and len(pf["groups"]) == 1331
        and len(dc["groups"]) == 1656,
        "coverage",
    )
    physical = {}
    checker = run_path(REPLAY / "decode_clock/transport/review_service.py")["group"]
    for i, order in enumerate(("RP", "PR"), 1):
        name = f"tesy-decode-service-20261125-r{i:02d}"
        rawmeta = read(66, name + "/receipt.json", decode["raw_receipt_sha256"][i - 1])
        path = name + "/raw/P.jsonl"
        file = archive / "part-66" / path
        check(
            sha(file) == rawmeta["arms"]["P"]["groups_sha256"] == checks[66][path]["sha256"],
            "pack prices",
        )
        prices = []
        total = 0
        with file.open() as stream:
            for p, line in zip(dc["groups"], stream, strict=True):
                row = json.loads(line)
                c, _ = checker(p, row, "P")
                total += c["common_set_floor"]
                layer = p["layer"]
                reads = {}
                for j in row["jobs"]:
                    lo, hi = j["read_spans_ns"][0]
                    reads[layer * 128 + j["expert"]] = hi - lo
                prices.append((reads, c["common_set_floor"]))
        clock = decode["arms"][order]["P"]["conditional"]["common_set_floor"]
        check(
            total == clock["inside_ns"] and total + 2_318_241_276 == clock["total_ns"],
            "paired clocks",
        )
        physical[order] = prices
    return actual, pri, bank, terminal, physical, cut, joint, fixed, origin


def summarize(groups, events):
    phases = {p: Counter() for p in ("call5", "call148", "decode")}
    for g, (disk, bank) in zip(groups, events, strict=True):
        c = phases[g["phase"]]
        if g["site"][2] >= 25:
            c["cuda_disk"] += len(g["logical_disk"])
            c["cuda_bank"] += g["logical_bank"]
            continue
        c["cpu_disk"] += len(disk)
        c["cpu_bank_read"] += len(bank)
        c["cpu_required_pages"] += len(g["pins"])
        c["cpu_resident_consumptions"] += len(g["pins"]) - len(disk) - len(bank)
        c["cpu_logical_hit_disk"] += len(set(disk) - g["new_demand"])
        c["cpu_logical_hit_bank_read"] += len(set(bank) - g["new_demand"])
    phases["prefill"] = phases["call5"] + phases["call148"]
    for c in phases.values():
        c["total_disk"] = c["cpu_disk"] + c["cuda_disk"]
        c["disk_payload_bytes"] = c["total_disk"] * PAY
        c["disk_pack_bytes"] = c["total_disk"] * STRIDE
        c["gpu_primary_set_payload_bytes"] = (c["cuda_bank"] + c["cuda_disk"]) * PAY
        c["cpu_bank_to_backing_bytes"] = c["cpu_bank_read"] * PAY
    return phases


def decode_prices(groups, events, physical):
    results = {}
    for order, marks in physical.items():
        c = Counter()
        for g, (miss, _), (seen, chain) in zip(groups, events, marks, strict=True):
            if g["site"][2] >= 25:
                c["cuda_callback_ns"] += chain
                continue
            priced = [seen[k] for k in miss if k in seen]
            c["cpu_read_only_callback_ns"] += max(priced, default=0)
            c["cpu_read_priced"] += len(priced)
            c["cpu_read_unpriced"] += len(miss) - len(priced)
            c["cpu_read_dropped_at_site"] += len(seen) - len(priced)
        c["decode_cuda_only_ns"] = 2_318_241_276 + c["cuda_callback_ns"]
        c["decode_witness_ns"] = c["decode_cuda_only_ns"] + c["cpu_read_only_callback_ns"]
        c["upper_47_tokens_s"] = 47 * NS / c["decode_witness_ns"]
        c["upper_46_evaluations_s"] = 46 * NS / c["decode_witness_ns"]
        results[order] = dict(c)
    return results


def cross(n, decode, joint, fixed):
    out = {}
    for p, arm in joint["arms"].items():
        # Exact fixed mean paid time per whole expert at this earlier population/mix.
        scale = Fraction(arm["P"]["service_ns"], 1058)
        for d, ns in decode.items():
            row = {}
            for label, gap in (
                ("serial", fixed["gaps"]["total_ns"]),
                ("pipeline", fixed["gaps"]["protected_ns"]),
                ("zero", 0),
            ):
                allowance = fixed["budget_prefill_plus_decode_ns"] - ns - gap
                row[label] = dict(
                    margin_ns=float(allowance - scale * n),
                    max_disk_jobs=allowance // scale,
                    min_useful_GBs=n * PAY / allowance if allowance > 0 else None,
                )
            row["six_tok_s_margin_ns"] = 47 * NS // 6 - ns
            out[f"{p}_{d}"] = row
    return out


def run(archive):
    groups, pri, bank, terminal, physical, cut, joint, fixed, origin = inputs(archive)
    pf = [g for g in groups if g["phase"] != "decode"]
    actual_gpu = fixed["work"]["prefill"]["disk_jobs"] - 661
    check(
        actual_gpu == sum(len(g["logical_disk"]) for g in pf if g["site"][2] >= 25) == 397,
        "CUDA unchanged",
    )
    results = {}
    budget = 1000 * PAY + 263 * STRIDE
    caps = {"P40": 40, "P1000": 1000, "U1263": 1263, "U_aligned": budget // STRIDE}
    check(caps["U_aligned"] == 1262, "aligned capacity")
    for name, cap in caps.items():
        unified = name.startswith("U")
        start = pri | bank if unified else pri
        free = set() if unified else bank
        goal = terminal | bank if unified else terminal
        partitioned = name == "P40"
        events, _ = solve(groups, start, free, cap, partitioned)
        continuous = summarize(groups, events)
        decode = decode_prices(groups[len(pf) :], events[len(pf) :], physical)
        pf_only, _ = solve(pf, start, free, cap, partitioned)
        pre = summarize(pf, pf_only)["prefill"]
        if len(goal) > cap and not partitioned:
            restored = {"status": "UNAVAILABLE_REQUIRED_SIMULTANEOUS_SET"}
        else:
            schedule_restore, restore = solve(pf, start, free, cap, partitioned, goal)
            done = summarize(pf, schedule_restore)["prefill"]
            n = done["total_disk"] + restore["disk"]
            restored = dict(
                status="MEMBERS_ONLY_WITH_FREE_PERMUTATIONS",
                reads_in_witness=done,
                last_group=restore,
                minimum_disk_including_restore=n,
                duplicated_payload_bytes_to_separate_if_unified=len(terminal & bank) * PAY
                if unified
                else 0,
                prices=cross(
                    n,
                    {k: v["conditional_decode_ns"] for k, v in fixed["pack_orders"].items()},
                    joint,
                    fixed,
                ),
            )
        if partitioned:
            check(
                pre["cpu_disk"] == cut["arms"]["carry"]["cases"]["no_required_exit"]["cpu"]
                and restored["minimum_disk_including_restore"] - actual_gpu
                == cut["arms"]["carry"]["cases"]["only_terminal_fixed"]["cpu"],
                "prior P40 oracle",
            )
        witness = cross(
            continuous["prefill"]["total_disk"],
            {k: v["decode_witness_ns"] for k, v in decode.items()},
            joint,
            fixed,
        )
        ideal = cross(
            pre["total_disk"],
            {k: v["decode_cuda_only_ns"] for k, v in decode.items()},
            joint,
            fixed,
        )
        results[name] = dict(
            capacity=cap,
            cpu_initial_distinct=len(start),
            fixed_cpu_bank=len(free),
            continuous=continuous,
            continuous_total_disk=continuous["prefill"]["total_disk"]
            + continuous["decode"]["total_disk"],
            continuous_decode_prices=decode,
            prefill_free_exit=pre,
            restore=restored,
            continuous_cross=witness,
            optimistic_cross=ideal,
            serial_decision="HEADROOM_FOR_FIXTURE_ONLY"
            if all(
                min(v["serial"]["margin_ns"], v["six_tok_s_margin_ns"]) >= 0
                for v in witness.values()
            )
            else "NO_GO_WITNESS_SERIAL_AT_ASSUMED_PRICES",
        )
    for objective in ("continuous_total_disk", "free_exit"):
        vals = [
            a["prefill_free_exit"]["total_disk"] if objective == "free_exit" else a[objective]
            for a in results.values()
        ]
        check(vals[0] >= vals[1] >= vals[2] and vals[3] >= vals[2], "capacity monotonicity")
    return dict(
        status="REPRODUCED_GLOBAL_CPU_RESIDENCY_R02",
        arms=results,
        initial=dict(
            cpu_primaries=len(pri),
            cpu_bank=len(bank),
            cpu_overlap=len(pri & bank),
            cuda_primaries=440,
            cuda_bank=90,
            cpu_primary_and_bank_budget_bytes=budget,
            t1_capture_bounds=origin["t1_prefix"],
        ),
        original_commit="aca7553d7f6d62da38e87517ccc1b888ee3b6e2e",
        archive_manifests=SEALS,
        prefill_plan_sha256=PF_PLAN,
        decode_plan_sha256=DC_PLAN,
        prior_oracle_sha256=CUT,
        joint_prices_sha256=JOINT,
        model_forwards=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "new-output-dir"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    try:
        signal.alarm(120)
        resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))
        git = ["git", "-C", str(HERE), "-c", "core.preloadIndex=false", "-c", "index.threads=1"]
        check(not subprocess.check_output([*git, "status", "--porcelain"]), "dirty checkout")
        result = run(a.archive)
        result.update(
            commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
            program_sha256=sha(Path(__file__)),
            protocol_sha256=sha(HERE / "protocol.md"),
        )
    except Exception as e:
        result = dict(status="FAIL_PRESERVED", reason=f"{type(e).__name__}: {e}")
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
