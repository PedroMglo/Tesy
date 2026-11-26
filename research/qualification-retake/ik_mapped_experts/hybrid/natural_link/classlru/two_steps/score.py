"""Replay one larger share-zero bank and verify the 161-slot bridge at every decision site."""

import argparse
from collections import Counter, OrderedDict
import ctypes
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from runpy import run_path
from struct import pack, unpack

HERE = Path(__file__).resolve().parent
PRE = run_path(str(HERE.parent / "score.py"))
BASE, PAGES, FULL = (PRE[k] for k in ("BASE", "PAGES", "FULL"))
need, sha = PRE["need"], PRE["sha"]
GRAPH = BASE["QUAL"]
NATIVE = "5971a0a1d830158ff7ec41432c06cb067e7e2dd641387b88c9ac2622143aaf1f"
POLICY = "3a5db71a2bdff977bfbc71d5974b79c2f1794f5391b14ff58cbe9926cd83aa6f"
LIBM = ctypes.CDLL("libm.so.6")
for f in (LIBM.exp2f, LIBM.log2f):
    f.argtypes = (ctypes.c_float,)
    f.restype = ctypes.c_float
PAYLOAD = BASE["PAYLOAD"]
MIB = 1 << 20


def f32(x):
    return unpack("f", pack("f", x))[0]


@lru_cache(maxsize=None)
def decay(age):
    return LIBM.exp2f(-age / 128)


class Bank:
    def __init__(self, cap, policy):
        self.cap = cap
        self.classes = policy == "classlru"
        self.queues = [OrderedDict() for _ in range(8 if self.classes else 1)]
        self.group = {}
        self.crf = {}
        self.last = {}
        self.clock = [0] * 36

    def relocate(self, key, dest):
        if key in self.group:
            del self.queues[self.group[key]][key]
        self.group[key] = dest
        self.queues[dest][key] = None

    def victim(self, protected):
        if not self.classes:
            k = next(iter(self.queues[0]))
            need(k not in protected, "LRU evicted an active key")
            return k
        best = None
        best_score = -1
        for c, q in enumerate(self.queues):
            k = next((k for k in q if k not in protected), None)
            if k is not None:
                score = (self.clock[k // 128] - self.last[k]) / (1 << c)
                if score > best_score:
                    best, best_score = k, score
        need(best is not None, "no victim")
        return best

    def plan(self, il, ids):
        keys = list(dict.fromkeys(128 * il + e for e in ids))
        demand = set(keys)
        missed = demand - self.group.keys()
        destination = {}
        for k in keys:
            c = 0
            if self.classes:
                age = self.clock[il] - self.last.get(k, -1)
                self.crf[k] = f32(f32(self.crf.get(k, 0) * decay(age)) + 1)
                self.last[k] = self.clock[il]
                c = min(7, int(LIBM.log2f(self.crf[k])))
            destination[k] = c
            if k not in missed:
                self.relocate(k, c)
        evictions = 0
        for k in sorted(missed):
            if len(self.group) == self.cap:
                old = self.victim(demand)
                del self.queues[self.group.pop(old)][old]
                evictions += 1
            self.relocate(k, destination[k])
        if self.classes:
            self.clock[il] += len(ids) // 4
        need(demand <= self.group.keys(), "unserved expert")
        return missed, evictions


def origin(current, last):
    if last is None:
        return "unseen"
    turn, call, tile = current
    old, previous, prev_tile = last
    if old != turn:
        return "T1"
    if turn == 2 and call >= 3 and previous >= 3:
        gap = call - previous
        need(gap >= 1, "two sightings per decode site")
        return "previous_decode" if gap == 1 else "two_or_more_decode"
    if turn == 2:
        return "T2_prefill"
    return "T1_prior"


def memory(policy):
    stock_dir = GRAPH / "stock_server_logits/physical-r2/receipt.json"
    need(
        sha(stock_dir) == "4e7055d10ebc748164326d03dec6e7659a4d26bdf9b4e28b16483d58c8e25120",
        "stock HTTP",
    )
    stock = json.loads(stock_dir.read_bytes())
    need(sha(policy) == stock["resource_policy_sha256"] == POLICY, "policy for target machine")
    cap = json.loads(policy.read_bytes())["gpu"]
    total, guard = int(cap["total_mib"]), int(cap["memory_stop_total_mib"])
    need(guard == total - 512, "GPU reserve")
    indexed = GRAPH / "ik_mapped_experts/header_index/result.json"
    need(
        sha(indexed) == "36209e35a8e04f672270108aeb70420f18b37c6536ced7eb906a66aa0f02234f",
        "header index",
    )
    bias = json.loads(indexed.read_bytes())["indexed"]["bias"]["bytes"]
    required = {}
    for k in (161, 288):
        n = 3 * ((((k + 1) * 4_406_400 + 127) // 128) * 128)
        required[k] = dict(
            real_slots=k, guard_slots=1, allocated_B=n, minimum_requested_MiB=-(-n // MIB)
        )
    peak = int(stock["sampled_peak_gpu_mib"]) * MIB
    delta = required[288]["allocated_B"] - required[161]["allocated_B"]
    return dict(
        geometry=required,
        delta_B=delta,
        extra_bias_B=bias,
        total_MiB=total,
        stop_MiB=guard,
        previous_stock_HTTP_peak_B=peak,
        projected_peak_same_other_B=peak + delta,
        projected_peak_all_bias_B=peak + delta + bias,
        remaining_to_stop_if_all_bias_B=guard * MIB - peak - delta - bias,
        stock_sha256=sha(stock_dir),
        resource_policy_sha256=POLICY,
        index_sha256=sha(indexed),
    )


def study(a):
    ref = HERE.parent / "result.json"
    need(sha(ref) == NATIVE, "previous native results")
    old = json.loads(ref.read_bytes())
    need(
        sha(a.ik / "src/llama-moe-cache-policy.h") == BASE["HDR"]
        and sha(a.ik / "src/llama-moe-cache.cpp") == BASE["HOOK"],
        "wrong planner sources",
    )
    need(
        BASE["IK"]["revision"](a.ik) == [BASE["IK"]["PIN"], BASE["IK"]["TREE"]], "wrong source pin"
    )
    ranks, g, _, sources = PAGES["reopen"](a.p97, a.p106)
    path = a.p106 / "ON/observer/events.pfj"
    cut, _ = FULL["metadata"](path, True)
    t1, initial = PRE["t1_sites"](FULL["iter_rows"](path, 0, cut), FULL["T1"])
    need(
        sum(len(row[-1]) for row in t1) == 4 * 74278
        and sum(initial.values()) == 1440
        and len(ranks) == 7012,
        "sealed route coverage",
    )
    sites = t1 + [(2, *k, [x % 128 for x in keys]) for k, keys in BASE["flatten"](ranks, g)]
    counters, comparisons, clocks = {}, {}, {}
    past = {}
    banks = {(kind, cap): Bank(cap, kind) for kind in ("lru", "classlru") for cap in (161, 288)}
    digests = {k: hashlib.sha256() for k in banks}
    for turn, call, tile, il, ids in sites:
        current = (turn, call, tile)
        tags = PRE["phases"](*current)
        tags = [t for t in tags if not t.startswith("T2_decode_call_")]
        if (turn, call) == (2, 3):
            tags.append("first_decode")
        coord = (turn, call, tile)
        demand = {128 * il + e for e in ids}
        misses = {}
        for key, cache in banks.items():
            absent, evictions = cache.plan(il, ids)
            hits = len(demand) - len(absent)
            misses[key] = absent
            digests[key].update(f"{hits} {len(absent)} {evictions}\n".encode())
            phases = counters.setdefault(f"{key[0]}_{key[1]}", {})
            for t in tags:
                phases.setdefault(t, Counter()).update(
                    sites=1,
                    rows=len(ids) // 4,
                    hits=hits,
                    fills=len(absent),
                    evictions=evictions,
                    payload_B=len(absent) * PAYLOAD,
                )
        for kind in ("lru", "classlru"):
            cmp = comparisons.setdefault(kind, {})
            narrow, big = misses[kind, 161], misses[kind, 288]
            for name, diff in (("saved", narrow - big), ("lost", big - narrow)):
                stamp = Counter(origin(current, past.get(k)) for k in diff)
                need("unseen" not in stamp, "initially empty cache hit an unseen key")
                for t in tags:
                    cmp.setdefault(t, {}).setdefault(name, Counter()).update(stamp)
        for k in demand:
            past[k] = coord
    for name in ("lru", "classlru"):
        for cap in (161, 288):
            tag = f"{name}_{cap}"
            clocks[tag] = {
                p: BASE["prices"](counters[tag][p]["fills"], n, d)
                for p, n, d in (("T2_through_first_final", 10, 1), ("T2_decode", 47, 6))
            }
        control = f"{name}_161"
        need(
            digests[name, 161].hexdigest() == old["results"][control]["per_site_census_sha256"],
            "native 161-site bridge " + name,
        )
        for p, v in old["results"][control]["phases"].items():
            need(
                all(
                    v[n] == counters[control][p][n] for n in ("hits", "fills", "evictions", "sites")
                ),
                "original phases " + p,
            )
        for p, typed in comparisons[name].items():
            need(
                sum(typed["saved"].values()) - sum(typed["lost"].values())
                == counters[name + "_161"][p]["fills"] - counters[name + "_288"][p]["fills"],
                "origins",
            )
    mem = memory(a.policy)
    choose = (
        all(
            clocks["classlru_288"][k]["payload_bytes"] < clocks["classlru_161"][k]["payload_bytes"]
            for k in clocks["classlru_288"]
        )
        and mem["remaining_to_stop_if_all_bias_B"] > 0
    )
    return dict(
        status="TRACE_DERIVED_TWO_STEP_BANK",
        method_sha256=sha(Path(__file__)),
        protocol_sha256=sha(HERE / "protocol.md"),
        p97=sources["p97_family"],
        p106=sources["p106_family"],
        route_sha256=sources["ordered_route"],
        t1_route=old["sources"]["t1_route"],
        header_sha256=BASE["HDR"],
        native_161_parent_sha256=NATIVE,
        first_capacity_test=288 if choose else 161,
        memory=mem,
        phases=counters,
        extra_hits_by_last_demand=comparisons,
        clocks=clocks,
        per_site_sha256={f"{k}_{c}": h.hexdigest() for (k, c), h in digests.items()},
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("p97", "p106", "ik", "policy", "new-output"):
        p.add_argument("--" + arg, type=Path, required=True)
    a = p.parse_args()
    a.new_output.mkdir(mode=0o700)
    try:
        r = study(a)
    except Exception as exc:
        r = {"status": "FAIL_PRESERVED", "error": str(exc)}
    temp = a.new_output / ".pending"
    with temp.open("x") as fp:
        json.dump(r, fp, indent=2, sort_keys=True)
        fp.write("\n")
    temp.rename(a.new_output / "receipt.json")
    print(r["status"], r.get("error", ""))
    raise SystemExit(r["status"] == "FAIL_PRESERVED")
