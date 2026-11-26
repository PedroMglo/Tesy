"""Replay a serialized exclusive victim swap on the qualified natural target trajectory."""

import argparse
import json
import os
import resource
import signal
import subprocess
from collections import Counter, OrderedDict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
N = HERE.parent
R = N / "replay"
T = R / "decode_clock/transport"
front = run_path(N / "prefill_frontier/screen.py")
pinned, require, digest = (front[k] for k in ("pinned", "check", "digest"))
F = "5225590f4a5ea17f7faa1d13fede10dc9abc771d53dbc388333709a4d86765c2"
PLAN = "aed09397a16ed706365d73e0d2535427528476b41d66e3d5e43ad90da345d79a"
PART65 = "1713b1e73b8e59c34b1f12fc268a9d6caafba09d5c82707476ec9a0febd0069b"
PAYLOAD = 13_219_200
PACK = 13_221_888
NSEC = 10**9


class Bank:
    """Membership changes only at ordered reservation transactions. No publish callback."""

    def __init__(self, cap, seed, primary):
        require(cap > 0 and len(seed) <= cap and len(set(seed)) == len(seed), "capacity or seed")
        self.cap = cap
        self.primary = set(primary)
        self.lru = OrderedDict.fromkeys(key for key in seed if key not in self.primary)
        self.initial = self.peak = len(self.lru)

    def reserve(self, incoming, victim):
        require(incoming not in self.primary, "reservation for resident")
        require(
            victim is None or (victim in self.primary and victim not in self.lru), "victim owner"
        )
        hit = incoming in self.lru
        if hit:
            del self.lru[incoming]
        evicted = None
        if victim is not None:
            self.primary.remove(victim)
            if len(self.lru) == self.cap:
                evicted, _ = self.lru.popitem(last=False)
            self.lru[victim] = None
        self.primary.add(incoming)
        self.peak = max(self.peak, len(self.lru))
        return hit, evicted


def ledger(groups, manager, seed, slots, tags, bases, previous):
    primary = {(n // 40, r[0]) for n, r in enumerate(slots) if r[0] >= 0}
    bank = Bank(353, seed, primary)
    mirror = [(r[0], r[1]) for r in slots]
    phases = {k: {"cpu": Counter(), "cuda": Counter()} for k in ("call5", "call148", "decode")}
    discards = Counter()
    seen_disk = set()
    cuts = []
    start = groups[0]["site"][0]
    decoder = []
    ranks = None
    previous_phase = None
    for group in groups:
        call, tile, layer, wave = site = group["site"]
        phase = "call5" if call == start else "call148" if call == start + 1 else "decode"
        if previous_phase != phase:
            cuts.append(len(bank.lru))
            previous_phase = phase
        if wave in (-1, 0):
            ranks = group["ranks"]
        else:
            require(not group["ranks"], "duplicated ranks")
        require(len(ranks) == group["rows"] * 4, "route vector")
        alloc, _ = manager.callback(layer, wave, ranks)
        c = phases[phase]["cpu" if layer < 25 else "cuda"]
        jobs = []
        for e, slot, gen, old, reason in alloc:
            i = layer * 40 + slot
            require(mirror[i] == (old, gen - 1), "victim generation")
            mirror[i] = (e, gen)
            incoming = (layer, e)
            victim = (layer, old) if old >= 0 else None
            hit, evicted = bank.reserve(incoming, victim)
            fixed = e in tags[layer]
            c["admissions"] += 1
            c["preloads"] += reason == 2
            c["static_disk"] += not fixed
            c["static_bank"] += fixed
            c["exclusive_disk"] += not hit
            c["exclusive_bank"] += hit
            c["kept_disk"] += not fixed and not hit
            c["eliminated_disk"] += not fixed and hit
            c["introduced_disk"] += fixed and not hit
            c["delivered_primary_bytes"] += PAYLOAD
            c["static_bank_delivered_bytes"] += PAYLOAD * fixed
            c["exclusive_bank_to_scratch_bytes"] += PAYLOAD * hit
            c["victim_to_bank_bytes"] += PAYLOAD * (victim is not None)
            c["exclusive_packed_fd_bytes"] += PACK * (not hit)
            if not hit:
                c["exclusive_gguf_fd_bytes"] += sum(
                    (((base + e * width) % 4096 + width + 4095) // 4096) * 4096
                    for base, width in bases[layer]
                )
                c["repeated_t2_disk_reads"] += incoming in seen_disk
                seen_disk.add(incoming)
            if evicted is not None:
                discards[(phase, "cpu" if evicted[0] < 25 else "cuda")] += 1
            jobs.append((e, slot, gen, fixed, hit))
        if phase == "decode":
            require(wave == -1 and len(jobs) <= 4, "decode shape")
            decoder.append((site, jobs))
    require(
        bank.primary.isdisjoint(bank.lru)
        and bank.primary == {(i // 40, pair[0]) for i, pair in enumerate(mirror) if pair[0] >= 0},
        "exclusive endpoint",
    )
    require(
        all(not p.possible_loading and p.next_wave == p.next_count for p in manager.pools),
        "outstanding primary loads",
    )
    phases["prefill"] = {t: phases["call5"][t] + phases["call148"][t] for t in ("cpu", "cuda")}
    static = previous["carry"]["variants"]["bank"]
    for phase, by_tier in phases.items():
        for t, c in by_tier.items():
            require(
                c["static_disk"] == static[phase][t]["disk_jobs"]
                and c["static_bank"] == static[phase][t].get("bank_hits", 0)
                and c["delivered_primary_bytes"] == static[phase][t]["primary_bytes"],
                "static trajectory by tier",
            )
            c["discarded_lru_keys_by_own_tier"] = (
                discards["call5", t] + discards["call148", t]
                if phase == "prefill"
                else discards[phase, t]
            )
        by_tier["all"] = by_tier["cpu"] + by_tier["cuda"]
    require(
        manager.emitted.hexdigest() == previous["carry"]["inferred_slot_stream_sha256"]
        and dict(manager.proofs) == previous["carry"]["induction"],
        "manager slot/induction",
    )
    return (
        decoder,
        phases,
        dict(
            capacity=bank.cap,
            seed=len(seed),
            initial_exclusive=bank.initial,
            removed_overlaps=len(seed) - bank.initial,
            peak=bank.peak,
            at_phase_entry=cuts,
            final=len(bank.lru),
            one_scratch_bytes=PAYLOAD,
        ),
    )


def clock_group(plan, raw, jobs, verifier):
    baseline, _ = verifier(plan, raw, "P")
    costs = {a["ordinal"]: sum(b - a for a, b in a["read_spans_ns"]) for a in raw["jobs"]}
    require(len(jobs) == len(plan["jobs"]) <= 4, "same admissions")
    alt = []
    unknown_reads = unknown_sets = 0
    for n, (j, (e, s, g, fixed, hit)) in enumerate(zip(plan["jobs"], jobs, strict=True)):
        require(
            (j["ordinal"], j["expert"], j["slot"], j["generation"], j["source"])
            == (n, e, s, g, "bank" if fixed else "disk"),
            "original identity",
        )
        require((n in costs) == (not fixed), "observed READ identity")
        unknown_reads += not hit and n not in costs
        unknown_sets += j["r0_same_site_set_ns"] is None
        alt.append((j["r0_same_site_set_ns"] or 0) + (0 if hit else costs.get(n, 0)))
    return baseline["common_set_floor"], max(alt, default=0), unknown_reads, unknown_sets


def calculate(archive):
    for f, h in (
        (R / "manager.py", "ceaa386d3d5994dd02ebc98d148378405bbf0fa46e98e06fd46a3cd48d44a05f"),
        (R / "screen.py", front["PROGRAMS"]["replay"][1]),
        (
            T / "review_service.py",
            "b09d9da0b01bda1a515397d640982c1fd21f10c440fe99318a111447b189daa2",
        ),
        (
            N / "prefill_frontier/screen.py",
            "a61f52ce1c310d54ae87fad5e3f16c656cc2ef47d423d6fe9f0dad547ce4f9ea",
        ),
    ):
        require(digest(f) == h, "source identity " + f.name)
    frontier = pinned(N / "prefill_frontier/evidence/receipt.json", F)
    h = frontier["origins"]
    p63, p65, p66 = (archive / f"part-{n}" for n in (63, 65, 66))
    manifests = [
        pinned(p / "manifest.json", v)["files"]
        for p, v in ((p63, h["archive63"]), (p65, PART65), (p66, h["archive66"]))
    ]
    fam = p63 / front["FAMILY_NAME"]
    hist = pinned(p63 / "tesy-policy-natural-replay-20261125-r02/receipt.json", h["replay"])
    service = pinned(p66 / front["REVIEW_NAME"], h["service"])
    plan_rel = "tesy-decode-transport-prepare-20261125-r01/plan.json"
    require(manifests[1][plan_rel]["sha256"] == service["plan_sha256"] == PLAN, "plan linkage")
    plan = pinned(p65 / plan_rel, PLAN)
    replay = run_path(R / "screen.py")
    rows, slots, words, calls, interval, tags, bases, origin = replay["sources"](fam, h["family"])
    require(all(hist[k] == v for k, v in origin.items()), "replay origin")
    sel = pinned(fam / "ON/before-t2-candidates.json", origin["t1_candidates_sha256"])
    seed = [tuple(k) for k in sel["capacities"]["353"]["ordered_keys"]]
    require(
        set(seed) == {(layer, e) for layer, members in enumerate(tags) for e in members},
        "initial tags",
    )
    groups, reads, work = replay["segment"](rows)
    require(work == hist["observed"], "R0 work")
    _, r0 = replay["trajectory"](
        groups,
        reads,
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
    require(r0 == hist["r0"], "full R0 reconstruction")
    manager = replay["Manager"](slots, words, calls, interval, tags)
    jobs, phases, state = ledger(groups, manager, seed, slots, tags, bases, hist)
    require(
        len(jobs) == len(plan["groups"]) == 1656
        and plan["causal_slot_stream_sha256"] == manager.emitted.hexdigest(),
        "decode trajectory",
    )
    verify = run_path(T / "review_service.py")["group"]
    prices = {}
    for i, order in enumerate(("RP", "PR"), 1):
        name = f"tesy-decode-service-20261125-r{i:02d}"
        meta = pinned(p66 / name / "receipt.json", service["raw_receipt_sha256"][i - 1])
        file = p66 / name / "raw/P.jsonl"
        require(
            meta["order"] == order
            and digest(file)
            == meta["arms"]["P"]["groups_sha256"]
            == service["arms"][order]["P"]["expected_data_sha256"]
            == manifests[2][name + "/raw/P.jsonl"]["sha256"],
            "physical pack work",
        )
        totals = Counter()
        with file.open() as stream:
            for (site, j), pg, line in zip(jobs, plan["groups"], stream, strict=True):
                require(
                    site == tuple(pg[k] for k in ("call", "tile", "layer", "wave")), "same callback"
                )
                old, new, unread, unset = clock_group(pg, json.loads(line), j, verify)
                totals.update(
                    static_ns=old,
                    exclusive_ns=new,
                    unpriced_reads=unread,
                    unpriced_sets=unset,
                    groups=1,
                )
        old_price = service["arms"][order]["P"]["conditional"]["common_set_floor"]
        require(
            totals["static_ns"] == old_price["inside_ns"]
            and totals["unpriced_reads"] == phases["decode"]["all"]["introduced_disk"],
            "old clock / new READs",
        )
        outside = old_price["total_ns"] - old_price["inside_ns"]
        duration = outside + totals["exclusive_ns"]
        pre = phases["prefill"]["all"]
        result = front["frontier"](
            pre["exclusive_disk"] * PAYLOAD,
            frontier["budget_prefill_plus_decode_ns"] - duration,
            frontier["gaps"]["total_ns"],
            frontier["gaps"]["protected_ns"],
        )
        prices[order] = dict(
            same_site=dict(totals),
            exterior_ns=outside,
            decode_lower_ns=duration,
            upper_rate_47=47 * NSEC / duration,
            upper_rate_46=46 * NSEC / duration,
            margin_six_47_ns=47 * NSEC // 6 - duration,
            margin_six_46_ns=46 * NSEC // 6 - duration,
            **result,
        )
    gains = {
        p: phases[p]["all"]["static_disk"] - phases[p]["all"]["exclusive_disk"]
        for p in ("prefill", "decode")
    }
    passed = min(gains.values()) > 0 and all(
        min(c["serial_margin_ns"], c["margin_six_47_ns"]) >= 0 for c in prices.values()
    )
    return dict(
        status="REPRODUCED_EXCLUSIVE_RESERVATION_BANK",
        decision="GO_FIXTURE_ONLY" if passed else "NO_GO_FOR_SERIAL_GATE_AT_FIXED_PRICES",
        disk_jobs_saved=gains,
        phases=phases,
        capacity=state,
        prices=prices,
        t1_costs_shared=origin["t1_prefix"],
        r0_reservations_checked=work["RESERVE"],
        static_slot_stream_sha256=manager.emitted.hexdigest(),
        source_seals=h,
        part65_manifest_sha256=PART65,
        plan_sha256=PLAN,
        frontier_sha256=F,
        outstanding_order_proof=dict(manager.proofs),
        model_forwards=0,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir(mode=0o700)
    try:
        signal.alarm(120)
        resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))
        git = ["git", "-C", str(HERE), "-c", "core.preloadIndex=false", "-c", "index.threads=1"]
        require(not subprocess.check_output([*git, "status", "--porcelain"]), "dirty checkout")
        result = calculate(a.archive)
        result.update(
            commit=subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
            program_sha256=digest(Path(__file__)),
            protocol_sha256=digest(HERE / "protocol.md"),
        )
    except Exception as e:
        result = dict(
            status="INCONCLUSIVE_SERVICE_ORDER"
            if type(e).__name__ == "OrderUnknown"
            else "FAIL_PRESERVED",
            reason=f"{type(e).__name__}: {e}",
        )
    with (a.new_output_dir / "receipt.json").open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")
    print(result["status"], result.get("reason", ""))
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
