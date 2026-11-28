"""Authenticate retention opportunities, construct finite schedules and price their generations."""

import argparse
import gzip
import hashlib
import heapq
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
RE = run_path(HERE / "replay.py")
SRC, CC, B, C, need = (RE[k] for k in ("SRC", "CC", "B", "C", "need"))
CAP, PAYLOAD = RE["CAP"], RE["PAYLOAD"]
METHOD = "264868b9e1282ced431c4fed4205b2b2c62690cac512bc4460e8faba2003fbc5"
CONTROL = "f458985b4f1417c3a5b434be4412da6b2a0eff744395d5e77dfc8459a1a615aa"


@dataclass(frozen=True)
class Reservation:
    incoming: tuple
    victim: tuple
    generation: tuple
    phase: str


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


def train(arm):
    select = run_path(HERE.parent / "selection.py")
    seal = SRC["pinned"](arm / "before-t2.json", select["T1_SEAL"])
    journal = arm / "observer/events.pfj"
    profile = select["PROFILE"]

    def rows():
        return profile["iter_rows"](journal, 0, seal["records"])

    grade, _ = profile["prefix_grade"](rows(), profile["T1"], 9)
    need(all(v == seal[k] for k, v in grade.items()) and seal["records"] == 87_736, "T1 boundary")
    counts = Counter((e.layer, e.expert) for e in rows() if e.kind == 11)
    return counts, grade["sha256"]


def opportunities(reservations, seed):
    available = dict.fromkeys(seed, 0)
    starts = {}
    for i, r in enumerate(reservations, 1):
        if r.incoming in available:
            starts[i] = available.pop(r.incoming)
        need(r.victim not in available and r.incoming != r.victim, "exclusive victim ownership")
        available[r.victim] = i
    return starts


def maximum_count(starts, capacity):
    active, keep = set(), set()
    for end, start in sorted(starts.items(), key=lambda item: (item[1], item[0])):
        active = {j for j in active if j > start}
        active.add(end)
        keep.add(end)
        if len(active) > capacity:
            remove = max(active)
            keep.remove(remove)
            active.remove(remove)
    return keep


def expensive_first(starts, prices, capacity):
    use = [0] * (max(starts, default=0) + 1)
    keep = set()
    for end in sorted(starts, key=lambda i: (-prices[i], i - starts[i], i)):
        start = starts[end]
        if max(use[start:end]) < capacity:
            keep.add(end)
            for t in range(start, end):
                use[t] += 1
    return keep


def assign(starts, chosen, capacity):
    free = list(range(capacity))
    busy, slots = [], {}
    peak = 0
    for end in sorted(chosen, key=lambda e: (starts[e], e)):
        start = starts[end]
        need(0 <= start < end, "invalid retention interval")
        while busy and busy[0][0] <= start:
            _, slot = heapq.heappop(busy)
            heapq.heappush(free, slot)
        need(free, "bank over capacity")
        slot = heapq.heappop(free)
        heapq.heappush(busy, (end, slot))
        slots[end] = slot
        peak = max(peak, len(busy))
    return slots, peak


def by_tier(key):
    return "CPU" if key[0] < 25 else "CUDA0"


def audit(reservations, seed, starts, slots, capacity):
    # Verify independently using source and consumer ownership, including same-transaction reuse.
    owners, offers, costs = {}, {}, defaultdict(Counter)
    for end, slot in slots.items():
        start = starts[end]
        key = reservations[end - 1].incoming
        need(0 <= slot < capacity, "invalid parking ID")
        if start:
            need(start not in offers and reservations[start - 1].victim == key, "wrong offer")
            offers[start] = (slot, key, end)
        else:
            need(key in seed and slot not in owners, "initial ownership")
            owners[slot] = (key, end)
    for i, r in enumerate(reservations, 1):
        if i in slots:
            need(owners.pop(slots[i]) == (r.incoming, i), "stale promotion")
            costs[by_tier(r.incoming)]["promotions"] += 1
        if i in offers:
            slot, key, end = offers[i]
            need(slot not in owners and key == r.victim, "overwritten parking slot")
            owners[slot] = (key, end)
            costs[by_tier(key)]["captures"] += 1
    need(not owners, "undrained interval schedule")
    return costs


def online(reservations, seed, counts, capacity):
    freq = counts.copy() if counts is not None else Counter()
    # The ordering within the sealed LRU seed is oldest first.
    held = {key: (freq[key], i - len(seed)) for i, key in enumerate(seed)}
    need(len(held) == len(seed) <= capacity, "initial bank")
    hits, costs = set(), defaultdict(Counter)
    peak = len(held)
    for i, r in enumerate(reservations, 1):
        if counts is not None:
            freq[r.incoming] += 1
        if r.incoming in held:
            hits.add(i)
            del held[r.incoming]
            costs[by_tier(r.incoming)]["promotions"] += 1
        need(r.victim not in held, "duplicate victim")
        held[r.victim] = (freq[r.victim], i)
        if len(held) > capacity:
            evicted = min(held, key=held.__getitem__)
            del held[evicted]
        if r.victim in held:
            costs[by_tier(r.victim)]["captures"] += 1
        peak = max(peak, len(held))
    return hits, costs, peak


def load_arm(archive, label, rows, seed, prior):
    (_, _, _), auth = B["read_arm"](archive, label, prior)
    waves, _ = SRC["timeline"](rows)
    groups, primary, _, witness = RE["ledger"](rows, waves, seed)
    txns = []
    ids = {}
    for e in rows:
        if e.kind == 11:
            key = SRC["key"](e)
            txns.append(Reservation((e.layer, e.expert), (e.layer, e.a), key, B["phase"](e.call)))
            ids[key] = len(txns)
    mandatory, lru = {}, set()
    jobs = defaultdict(lambda: defaultdict(list))
    for (call, tile, layer), records in groups.items():
        for r in records:
            i = ids[r.key]
            if r.renewal_hit:
                lru.add(i)
            if r.mandatory:
                jobs[call][tile, layer].append(RE["Job"](i, r.price.read_ns, r.price.set_ns))
                mandatory[i] = r.price.read_ns + r.price.set_ns
    host = SRC["NATIVE"]["host_trace"](rows)
    regs = list(C["partition"](host["calls"], waves, jobs))
    lineage = (auth["trajectory_sha256"], witness["semantic_reservations_sha256"])
    return (regs, auth["outside_calls_ns"]), txns, primary, mandatory, lru, lineage


def run(archive, control_path, out):
    need(SRC["digest"](HERE / "intervals.md") == METHOD, "prospective method")
    control = SRC["pinned"](control_path, CONTROL)
    prior = SRC["pinned"](B["NATURAL"] / "prefill_retention/request_cost/receipt.json", B["PRIOR"])
    root = archive / "part-106" / SRC["SOURCES"]["P106"][0]
    counts, prefix = train(root / "ON")
    seal, rows106, _, _ = SRC["Q"]["read_new"](root, SRC["SOURCES"]["P106"][1])
    seed = list(map(tuple, seal["banks"]["lru"]["ordered_keys"]))
    data, summed = {}, Counter()
    common = None
    for label in ("P106", "P97"):
        rows = rows106
        if label == "P97":
            path = archive / "part-97" / SRC["SOURCES"][label][0] / "ON/raw/events.pfj"
            rows, _ = SRC["T"]["PFJ"]["read_journal"](path)
        data[label], txns, primary, prices, lru, lineage = load_arm(
            archive, label, rows, seed, prior[label]
        )
        identity = (txns, primary, prices.keys(), lru, lineage)
        need(common is None or common == identity, "different reservation, phase, owner or route")
        common = identity
        summed.update(prices)
    seed = [key for key in seed if key not in primary]
    starts = opportunities(txns, seed)
    needed = {i: start for i, start in starts.items() if i in summed}
    recent, recent_cost, recent_peak = online(txns, seed, None, CAP)
    need(recent == lru, "renewed control generation mismatch")
    frequent, freq_cost, freq_peak = online(txns, seed, counts, CAP)
    decisions = {
        "recent": recent,
        "frequency": frequent,
        "count_oracle": maximum_count(needed, CAP),
        "price_oracle": expensive_first(needed, summed, CAP),
        "unlimited_eligible": set(needed),
    }
    proof, results = {}, {}
    for name, chosen in decisions.items():
        capacity = len(needed) if name == "unlimited_eligible" else CAP
        slots, peak = assign(starts, chosen, capacity)
        costs = audit(txns, seed, starts, slots, capacity)
        capture_scope = "selected_intervals_only"
        if name in ("recent", "frequency"):
            actual, peak = (
                (recent_cost, recent_peak) if name == "recent" else (freq_cost, freq_peak)
            )
            for tier, c in costs.items():
                need(
                    c["promotions"] == actual[tier]["promotions"]
                    and c["captures"] <= actual[tier]["captures"],
                    "causal accounting",
                )
            costs, capture_scope = actual, "all_online_admissions"
        for c in costs.values():
            for op in ("captures", "promotions"):
                c[op + "_payload_bytes"] = c[op] * PAYLOAD
        proof[name] = [[starts[i], i, slots[i]] for i in sorted(chosen)]
        clocks = {m: CC["assess"](data, chosen, m == "direct") for m in ("copied", "direct")}
        if name == "recent":
            for m in clocks:
                need(clocks[m] == control["causal"]["renewed_" + m], "four control clocks")
        phase = Counter(txns[i - 1].phase for i in chosen if i in needed)
        results[name] = {
            "mandatory_hits_by_phase": phase,
            "all_hits": len(chosen),
            "capacity": capacity if name != "unlimited_eligible" else None,
            "peak": peak,
            "payload_by_tier": costs,
            "capture_scope": capture_scope,
            "witness_sha256": digest(proof[name]),
            "clocks": clocks,
        }
    floor = results["unlimited_eligible"]["clocks"]["direct"]["with_full_client_cost_ns"]
    for res in results.values():
        observed = res["clocks"]["direct"]["with_full_client_cost_ns"]
        need(all(floor[a][k] <= observed[a][k] for a in floor for k in floor[a]), "invalid floor")
    floor_grant = results["unlimited_eligible"]["clocks"]["direct"]["fits_with_grant"]
    oracle_full = any(
        all(
            B["joint"](c) >= 0
            for c in results[n]["clocks"]["direct"]["with_full_client_cost_ns"].values()
        )
        for n in ("count_oracle", "price_oracle")
    )
    freq = results["frequency"]["clocks"]["direct"]
    proof_bytes = gzip.compress((json.dumps(proof, separators=(",", ":")) + "\n").encode(), mtime=0)
    (out / "schedule.json.gz").write_bytes(proof_bytes)
    return {
        "schema": "tesy.ready_bank_intervals.v1",
        "status": "TRACE_DERIVED",
        "method_sha256": METHOD,
        "source_sha256": SRC["digest"](Path(__file__)),
        "parent_sha256": CONTROL,
        "t1_prefix_sha256": prefix,
        "t1_reservations": sum(counts.values()),
        "routing_and_reservations": lineage,
        "schedule_sha256": hashlib.sha256(proof_bytes).hexdigest(),
        "initial_secondary": len(seed),
        "reservations": len(txns),
        "mandatory": len(summed),
        "eligible_mandatory": len(needed),
        "results": results,
        "decisions": {
            "frequency_even_with_grant": "NO_GO"
            if not freq["fits_with_grant"]
            else "GO_CAPTURE_FIXTURE_ONLY"
            if not freq["p106_first_needed_credit_ns"]
            else "INCONCLUSIVE",
            "finite_capacity": "HEADROOM_ONLY"
            if oracle_full
            else "INCONCLUSIVE"
            if floor_grant
            else "NO_GO",
        },
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--control", type=Path, required=True)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a.archive, a.control, a.new_output_dir)
    except FileNotFoundError as e:
        path = Path(e.filename).resolve()
        status = "NOT_RUN_RAW_REQUIRED" if path.is_relative_to(a.archive.resolve()) else "FAIL"
        result = {"status": status, "missing": path.name}
    except (ValueError, KeyError, AssertionError, OSError, TypeError) as e:
        result = {"status": "FAIL", "reason": str(e)}
    tmp = a.new_output_dir / ".pending"
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    print(result["status"], result.get("decisions", result.get("reason", "")))
    raise SystemExit(result["status"] != "TRACE_DERIVED")
