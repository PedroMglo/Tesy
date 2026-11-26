"""Recover expert and bank-slot adjacency at each share-zero ClassLRU dispatch."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parents[1] / "natural_link/classlru/two_steps"
STEP = run_path(str(PARENT / "score.py"))
PRE, BASE = STEP["PRE"], STEP["BASE"]
need, sha, SLAB = STEP["need"], STEP["sha"], 4_406_400
STATE_RECEIPT = "8dd73ee6625e0d7dc2e93f2f6cf919c390fad6eb5d91391e06f89ddd2db588db"


class KeySlots(STEP["Bank"]):
    """Attach the exact initial slot, or the selected victim's slot, to each key."""

    def __init__(self, capacity):
        super().__init__(capacity, "classlru")
        self.slot = {}
        self.freed = None
        self.fills = []

    def victim(self, protected):
        key = super().victim(protected)
        need(self.freed is None, "unused victim slot")
        self.freed = self.slot.pop(key)
        return key

    def relocate(self, key, dest):
        if key not in self.group:
            slot = self.freed if self.freed is not None else len(self.slot)
            need(0 <= slot < self.cap and key not in self.slot, "no admissible slot")
            self.slot[key] = slot
            self.freed = None
            self.fills.append((key % 128, slot))
        super().relocate(key, dest)


class SlotQueues:
    """Direct slot representation. Class zero initially contains every empty slot."""

    def __init__(self, capacity):
        self.queues = [list(range(capacity)), *([] for _ in range(7))]
        self.slot_class = [0] * capacity
        self.key_at = [None] * capacity
        self.mapping = {}
        self.crf = {}
        self.last = {}
        self.clock = [0] * 36

    def move(self, slot, rank):
        self.queues[self.slot_class[slot]].remove(slot)
        self.slot_class[slot] = rank
        self.queues[rank].append(slot)

    def select(self, protected):
        best_slot, best_score = None, -1
        for rank, queue in enumerate(self.queues):
            for slot in queue:
                old = self.key_at[slot]
                if old is None:
                    return slot
                if old in protected:
                    continue
                age = self.clock[old // 128] - self.last[old]
                score = age / (2**rank)
                if score > best_score:
                    best_slot, best_score = slot, score
                break
        need(best_slot is not None, "every slot protected")
        return best_slot

    def plan(self, layer, ids):
        f32 = STEP["f32"]
        keys = list(dict.fromkeys(layer * 128 + expert for expert in ids))
        protected = set(keys)
        rank = {}
        for key in keys:
            age = self.clock[layer] - self.last.get(key, -1)
            crf = f32(1.0 + f32(self.crf.get(key, 0.0) * STEP["decay"](age)))
            self.crf[key], self.last[key] = crf, self.clock[layer]
            rank[key] = min(7, int(STEP["LIBM"].log2f(crf)))
            if key in self.mapping:
                self.move(self.mapping[key], rank[key])
        fills, evictions = [], 0
        for key in sorted(protected):
            if key in self.mapping:
                continue
            slot = self.select(protected)
            old = self.key_at[slot]
            if old is not None:
                del self.mapping[old]
                evictions += 1
            self.mapping[key] = slot
            self.key_at[slot] = key
            self.move(slot, rank[key])
            fills.append((key % 128, slot))
        self.clock[layer] += len(ids) // 4
        return fills, evictions


def runs(fills):
    lengths = []
    previous = None
    for e, slot in fills:
        if previous and (previous[0] + 1, previous[1] + 1) == (e, slot):
            lengths[-1] += 1
        else:
            lengths.append(1)
        previous = (e, slot)
    return lengths


def load_sites(p97, p106, prior):
    pages, full = STEP["PAGES"], STEP["FULL"]
    ranks, geometry, _, sources = pages["reopen"](p97, p106)
    need(sources["ordered_route"] == prior["route_sha256"] and len(ranks) == 7012, "T2 routes")
    pfj = p106 / "ON/observer/events.pfj"
    cut, _ = full["metadata"](pfj, True)
    seal = json.loads((p106 / "ON/before-t2.json").read_bytes())
    need(seal["records"] == cut and seal["route_sha256"] == prior["t1_route"], "T1 cut")
    t1, _ = PRE["t1_sites"](full["iter_rows"](pfj, 0, cut), full["T1"])
    need(sum(len(row[-1]) for row in t1) == 4 * 74278, "T1 routes")
    return t1 + [(2, *k, [x % 128 for x in keys]) for k, keys in BASE["flatten"](ranks, geometry)]


def aggregate(c):
    histogram = dict(sorted((k, v) for k, v in c.items() if isinstance(k, int)))
    fills = sum(k * v for k, v in histogram.items())
    roles = 3
    return {
        "sites": c["sites"],
        "zero_fill_sites": c["empty"],
        "get_ids_bytes": c["rank_ids"] * 4,
        "ids_get_sync_calls": c["sites"],
        "map_set_calls": c["sites"],
        "map_set_bytes": 128 * 4 * c["sites"],
        "runs_per_role": histogram,
        "fills": fills,
        "weight_set_calls": roles * sum(histogram.values()),
        "singleton_bytes": roles * SLAB * histogram.get(1, 0),
        "multi_fill_bytes": roles * SLAB * (fills - histogram.get(1, 0)),
    }


def study(args):
    ik = BASE["IK"]
    need(ik["revision"](args.ik) == [ik["PIN"], ik["TREE"]], "ik pin")
    ik["require_clean"](args.ik)
    need(sha(args.ik / "src/llama-moe-cache.cpp") == BASE["HOOK"], "hook")
    need(sha(args.ik / "src/llama-moe-cache-policy.h") == BASE["HDR"], "policy")
    prior_file = PARENT / "result.json"
    need(sha(prior_file) == STATE_RECEIPT, "two-step control")
    prior = json.loads(prior_file.read_bytes())
    sites = load_sites(args.p97, args.p106, prior)
    results = {}
    with (args.new_output / "sites.jsonl").open("x") as records:
        for capacity in (161, 288):
            tag = f"classlru_{capacity}"
            keys, slots = KeySlots(capacity), SlotQueues(capacity)
            census, counts = hashlib.sha256(), {}
            for turn, call, tile, layer, ids in sites:
                keys.fills.clear()
                missing, evictions = keys.plan(layer, ids)
                fills, victims = slots.plan(layer, ids)
                need(keys.fills == fills and keys.slot == slots.mapping, "per-site slot mismatch")
                need(keys.clock == slots.clock and keys.freed is None, "clock or unfinished fill")
                need(len(missing) == len(fills) and victims == evictions, "census")
                hits = len(set(ids)) - len(fills)
                census.update(f"{hits} {len(fills)} {evictions}\n".encode())
                lengths = runs(fills)
                need(sum(lengths) == len(fills), "run length conservation")
                tags = [
                    t
                    for t in PRE["phases"](turn, call, tile)
                    if not t.startswith("T2_decode_call_")
                ]
                if (turn, call) == (2, 3):
                    tags.append("first_decode")
                for phase in tags:
                    c = counts.setdefault(phase, Counter())
                    c.update(sites=1, empty=int(not fills), rank_ids=len(ids))
                    c.update(lengths)
                records.write(
                    json.dumps(
                        [capacity, turn, call, tile, layer, fills, lengths], separators=(",", ":")
                    )
                    + "\n"
                )
            need(census.hexdigest() == prior["per_site_sha256"][tag], "previous site census")
            results[tag] = {phase: aggregate(c) for phase, c in counts.items()}
            for phase, row in results[tag].items():
                old = prior["phases"][tag][phase]
                need((row["sites"], row["fills"]) == (old["sites"], old["fills"]), "cohort")
                need(row["multi_fill_bytes"] + row["singleton_bytes"] == old["payload_B"], "bytes")
    return dict(
        status="TRACE_DERIVED_CLASSLRU_FILL_RUNS",
        previous=STATE_RECEIPT,
        method=sha(Path(__file__)),
        protocol=sha(HERE / "protocol.md"),
        ik_commit=ik["PIN"],
        hook=BASE["HOOK"],
        header=BASE["HDR"],
        t1_route=prior["t1_route"],
        t2_route=prior["route_sha256"],
        sites_sha256=sha(args.new_output / "sites.jsonl"),
        phases=results,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("p97", "p106", "ik", "new-output"):
        p.add_argument("--" + name, type=Path, required=True)
    args = p.parse_args()
    args.new_output.mkdir(mode=0o700, exist_ok=False)
    try:
        result = study(args)
    except Exception as error:
        result = {"status": "FAIL_PRESERVED", "reason": str(error)}
    tmp = args.new_output / ".pending"
    with tmp.open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2)
        f.write("\n")
    tmp.rename(args.new_output / "receipt.json")
    print(result["status"])
    return int(result["status"] == "FAIL_PRESERVED")


if __name__ == "__main__":
    raise SystemExit(main())
