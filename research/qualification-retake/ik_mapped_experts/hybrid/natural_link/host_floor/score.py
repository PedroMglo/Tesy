"""Offline lower bound on missing expert bytes with one pooled, bypassable store."""

import argparse
import heapq
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
LRU = run_path(str(HERE.parent / "score.py"))
PAGES = LRU["PAGES"]
need, sha = LRU["need"], LRU["sha"]
PAYLOAD = LRU["PAYLOAD"]
LRU_COMPACT = "4ea1270383e0876a709139b9dbc19c2c4244c6d976056494f08034b4a2f1adac"
PHASES = {
    "prefill": (1, 2),
    "through_first_final": (1, 46),
    "all_decode": (3, 48),
    "all_T2": (1, 48),
}


def optimal(groups, slots):
    """Minimize fetches at layer boundaries with free initial state and streaming misses."""
    if slots < 0:
        raise ValueError("negative capacity")
    future = {}
    following = []
    for i in range(len(groups) - 1, -1, -1):
        group = groups[i]
        if len(set(group)) != len(group):
            raise ValueError("duplicate key in the same layer group")
        following.append([(key, future.get(key)) for key in group])
        future.update(dict.fromkeys(group, i))
    entries = heapq.nsmallest(slots, future, key=lambda k: (future[k], k))
    bank = {key: future[key] for key in entries}
    victims = [(-time, key) for key, time in bank.items()]
    heapq.heapify(victims)
    misses = 0
    for batch in reversed(following):
        for key, next_use in batch:
            if key not in bank:
                misses += 1
            if next_use is None:
                bank.pop(key, None)
            else:
                bank[key] = next_use
                heapq.heappush(victims, (-next_use, key))
        # All requests can stream through the current layer without occupying a slot.
        # Retain the keys needed soonest at a later layer; stale priorities are harmless.
        while len(bank) > slots:
            negative, key = heapq.heappop(victims)
            if bank.get(key) == -negative:
                del bank[key]
    return misses


def ceil_ratio(num, den):
    return -(-num // den)


def estimate(groups, host_gib, gpu_slots, lru, phase):
    accessible = (host_gib << 30) + gpu_slots * PAYLOAD
    cap = ceil_ratio(accessible, PAYLOAD)
    misses = optimal(groups, cap)
    disk = misses * PAYLOAD
    r = {
        "equivalent_slots_rounded_up": cap,
        "minimum_fetches_relaxed": misses,
        "minimum_source_B": disk,
        "pooled_B_assumed": accessible,
        "extra_B_granted_by_rounding": cap * PAYLOAD - accessible,
    }
    if phase not in ("through_first_final", "all_decode"):
        return r
    dur_num, dur_den = (10, 1) if phase == "through_first_final" else (47, 6)
    gpu = lru["budgets"][str(gpu_slots)]["phases"][phase]["any_start_payload_B"][0]
    r.update(
        minimum_source_B_s=ceil_ratio(disk * dur_den, dur_num),
        lru_gpu_minimum_B=gpu,
        budgets={},
    )
    for speed in (4_500_000_000, 8_000_000_000):
        ssd_ns = ceil_ratio(disk * 10**9, speed)
        gpu_ns = ceil_ratio(gpu * 10**9, LRU["CEILING"])
        floor_ns = max(ssd_ns, gpu_ns)
        r["budgets"][str(speed)] = {
            "nvme_floor_ns": ssd_ns,
            "gpu_floor_ns": gpu_ns,
            "joint_floor_ns": floor_ns,
            "remaining_ns": dur_num * 10**9 // dur_den - floor_ns,
            "infeasible": max(disk * dur_den * LRU["CEILING"], gpu * dur_den * speed)
            > dur_num * speed * LRU["CEILING"],
        }
    return r


def run(a):
    ref = HERE.parent / "result.json"
    need(sha(ref) == LRU_COMPACT, "changed LRU result")
    lru = json.loads(ref.read_bytes())
    need(sha(a.inventory) == PAGES["IK"]["INVENTORY"], "changed C283 inventory")
    geometry = PAGES["IK"]["layer_geometry"](a.inventory.read_bytes())
    ranges = sorted((base, base + 128 * PAGES["STRIDE"]) for bases in geometry for base in bases)
    need(
        len(ranges) == 108
        and all(e <= s for (_, e), (s, _) in zip(ranges[:-1], ranges[1:], strict=True)),
        "payload overlap",
    )
    ranks, geom, _, sources = PAGES["reopen"](a.p97, a.p106)
    sites = LRU["flatten"](ranks, geom)
    need(
        len(geom) == 48
        and len(ranks) == 7012
        and sources["ordered_route"] == lru["sources"]["ordered_route"],
        "route/geometry",
    )
    result = {}
    for phase, (lo, hi) in PHASES.items():
        groups = [tuple(dict.fromkeys(ids)) for (call, _, _), ids in sites if lo <= call <= hi]
        result[phase] = {
            "unique_lookups": sum(map(len, groups)),
            "distinct_keys": len(set().union(*map(set, groups))),
            "cases": {
                f"{host}GiB+{gpu}": estimate(groups, host, gpu, lru, phase)
                for host in (10, 20, 32)
                for gpu in (128, 161)
            },
        }
    return {
        "status": "FORMAL_CONDITIONAL_POOLED_SOURCE_FLOOR",
        "sources": sources
        | {"lru": sha(ref), "protocol": sha(HERE / "protocol.md"), "script": sha(Path(__file__))},
        "expert_B": PAYLOAD,
        "phases": result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ("p97", "p106", "inventory", "new-output"):
        parser.add_argument("--" + label, required=True, type=Path)
    a = parser.parse_args()
    a.new_output.mkdir(mode=0o700)
    try:
        receipt = run(a)
    except Exception as error:
        receipt = {"status": "FAIL_PRESERVED", "reason": str(error)}
    temp = a.new_output / ".pending"
    temp.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    temp.replace(a.new_output / "receipt.json")
    print(receipt["status"], receipt.get("reason", ""))
    return receipt["status"] == "FAIL_PRESERVED"


if __name__ == "__main__":
    raise SystemExit(main())
