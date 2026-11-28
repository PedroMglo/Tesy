"""Replay a two-pool causal secondary bank under different legal prefill reservation orders."""

import argparse
import gzip
import hashlib
import heapq
import json
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
R = run_path(HERE / "review.py")
K, P, need, SRC, E = (R[k] for k in ("K", "P", "need", "SRC", "E"))
IV = run_path(HERE.parents[2] / "renewal/intervals.py")
PAYLOAD = K["PAYLOAD"]


def stage(layer):
    return int(layer >= 25)


def quotas(freq):
    demand = sum(freq.values())
    need(demand > 0, "empty training")
    front = sum(n for (layer, _), n in freq.items() if stage(layer) == 0)
    q = (2 * 353 * front + demand) // (2 * demand)
    return [q, 353 - q]


class Pool:
    def __init__(self, capacity, seed, freq):
        self.capacity = capacity
        self.freq = freq.copy()
        self.held = {}
        self.priority = {}
        self.free = list(range(capacity))
        self.tick = 0
        for i, key in enumerate(seed[-capacity:] if capacity else []):
            self.held[key] = heapq.heappop(self.free)
            self.priority[key] = (self.freq[key], i - len(seed))
        self.peak = len(self.held)

    def reserve(self, key, victim):
        self.tick += 1
        self.freq[key] += 1
        source = self.held.pop(key, None)
        if source is not None:
            del self.priority[key]
            heapq.heappush(self.free, source)
        need(victim not in self.held and key != victim, "secondary/primary collision")
        dest = None
        if self.capacity:
            rank = (self.freq[victim], self.tick)
            if not self.free:
                low = min(self.priority, key=self.priority.__getitem__)
                if self.priority[low] < rank:
                    heapq.heappush(self.free, self.held.pop(low))
                    del self.priority[low]
            if self.free:
                dest = heapq.heappop(self.free)
                self.held[victim] = dest
                self.priority[victim] = rank
        self.peak = max(self.peak, len(self.held))
        need(len(self.held) + len(self.free) == self.capacity, "slot conservation")
        return source, dest


def run_order(tx, init, seed, freq, caps, lead):
    # The ordered subsequence of transactions on each stage is unchanged by the interleaving.
    primary = {(layer, idx): (e, gen) for layer, idx, e, gen in init}
    present = {(layer, e) for (layer, _), (e, _) in primary.items()}

    def group(layer):
        return stage(layer) if len(caps) == 2 else 0

    pools = [
        Pool(cap, [k for k in seed if k not in present and group(k[0]) == i], freq)
        for i, cap in enumerate(caps)
    ]
    entry = [len(p.held) for p in pools]
    order = list(range(len(tx)))
    if lead:
        # A1, A2, B1, A3, B2, A4, B3, A5, B4, B5. Calls 1 and 3+ stay in order.
        def ordinal(i):
            call, tile, layer, *_ = tx[i]
            if call != 2:
                return call, 0
            return call, (max(0, 2 * tile - 3) if not stage(layer) else min(9, 2 * tile))

        order.sort(key=ordinal)
    effect = [None] * len(tx)
    traffic = defaultdict(Counter)
    counts = Counter()
    last_tail = {tx[i][1]: i for i in order if tx[i][0] == 2 and stage(tx[i][2])}
    need(set(last_tail) == set(range(1, 6)), "all five tile tails")
    live = set()
    for i in order:
        c, tile, layer, slot, gen, e, old = tx[i]
        owner = group(layer)
        need(primary[layer, slot] == (old, gen - 1), "primary generation")
        primary[layer, slot] = e, gen
        src, dst = pools[owner].reserve((layer, e), (layer, old))
        effect[i] = [owner, src, dst]
        phase = "prefill" if c <= 2 else "early_decode" if c <= 46 else "tail"
        line = traffic[phase, "front" if not stage(layer) else "tail"]
        line.update(jobs=1, hits=int(src is not None), captures=int(dst is not None))
        counts[phase] += src is not None
        if c == 2:
            live.add(tile)
            # A tile is done after the last reservation of its tail (positive on every T2 tile).
            need(len(live) <= 2, "tile capacity")
            if i == last_tail[tile]:
                live.remove(tile)
    need(not live and len(primary) == 1440, "final consumer state")
    record = {}
    for (phase, tier), v in traffic.items():
        record.setdefault(phase, {})[tier] = dict(
            **v,
            nvme_payload=(v["jobs"] - v["hits"]) * PAYLOAD,
            promoted_payload=v["hits"] * PAYLOAD,
            captured_payload=v["captures"] * PAYLOAD,
        )
    final = [sorted((layer, e, sl) for (layer, e), sl in p.held.items()) for p in pools]
    return effect, dict(
        hits=dict(counts),
        traffic=record,
        initial=entry,
        peak=[p.peak for p in pools],
        final_occupancy=[len(p.held) for p in pools],
        final_sha256=hashlib.sha256(json.dumps(final).encode()).hexdigest(),
    )


def priced(tag, bank_by_site, data, paths, layout, pipeline):
    # The frozen pricer indexes both available sources and disk positions by a domain.
    # With renewal that domain is the full site. Its third coordinate is the real layer.
    groups, order_by_site, labels = [], {}, []
    for call, tile, layer, *clock_and_work in data["groups"]:
        site = call, tile, layer
        order_by_site[site] = paths[layer]
        labels.extend((site, e) for e in bank_by_site.get(site, ()))
        groups.append([call, tile, site, *clock_and_work])
    arg = (
        dict(calls=data["calls"], groups=groups),
        layout["arms"][tag],
        pipeline["arms"][tag]["markers"],
        order_by_site,
        labels,
    )
    return {m: K["calculate"](*arg, direct) for m, direct in (("copied", False), ("direct", True))}


def assess(w):
    freq = Counter({(layer, e): v for layer, e, v in w["counts"]})
    need(sum(freq.values()) == 5727, "training source")
    seed = list(map(tuple, w["seed"]))
    caps = quotas(freq)
    tx = w["reservations"]
    need(len(tx) == 2354 and len(seed) == len(set(seed)) == 353, "ledger")
    init = w["initial"]
    serial, old = run_order(tx, init, seed, freq, [353], False)
    lead, other = run_order(tx, init, seed, freq, [353], True)
    need(sum(old["hits"].values()) == 691, "known serial frequency")
    result = dict(
        caps=caps,
        global_serial=old,
        global_leading=other,
        different_global_hit_decisions=sum(
            (a[1] is None) != (b[1] is None) for a, b in zip(serial, lead, strict=True)
        ),
    )
    causal, info = run_order(tx, init, seed, freq, caps, False)
    parallel, check = run_order(tx, init, seed, freq, caps, True)
    need(causal == parallel and info == check, "order-sensitive tier ownership")
    set_seed = set(seed)
    served = defaultdict(set)
    fixed = defaultdict(set)
    for (call, tile, layer, _, _, e, _), (_, source, _) in zip(tx, causal, strict=True):
        if source is not None:
            served[call, tile, layer].add(e)
        if (layer, e) in set_seed:
            fixed[call, tile, layer].add(e)
    result["partition"] = info
    result["witness_sha256"] = hashlib.sha256(
        json.dumps(causal, separators=(",", ":")).encode()
    ).hexdigest()
    layout = R["get"](E / "layout.json")
    pipeline = R["get"](E / "pipeline.json")
    baseline = R["get"](E / "bank.json")
    plan = R["get"](E / "plan.json")
    service = R["unpack"]("service.json.gz")
    need(service["selected"] == w["seed"], "frozen sources")
    arms = {}
    for tag, raw in service["journals"].items():
        modes = {}
        for name, path in (("numeric", [list(range(128))] * 36), ("trained", plan["order"])):
            control = priced(tag, fixed, raw, path, layout, pipeline)
            for mode, v in control.items():
                oldrow = baseline["arms"][tag]["fixed_" + name]
                need(
                    v["counts"] == oldrow["population"] and v["limits_by_Bps"] == oldrow[mode],
                    "fixed-bank control differs",
                )
            modes[name] = priced(tag, served, raw, path, layout, pipeline)
        arms[tag] = modes
    result["arms"] = arms
    return result


def observe(archive):
    name, h, _ = SRC["SOURCES"]["P106"]
    t1 = archive / "part-106" / name / "ON"
    freq, prefix = IV["train"](t1)
    raw = R["unpack"]("service.json.gz")
    result = dict(
        counts=[[layer, e, v] for (layer, e), v in sorted(freq.items())],
        seed=raw["selected"],
        prefix_sha256=prefix,
    )
    for tag in ("P106", "P97"):
        name, h, _ = SRC["SOURCES"][tag]
        root = archive / ("part-" + tag[1:]) / name
        if tag == "P106":
            sel, rows, _, proof = SRC["Q"]["read_new"](root, h)
            need(
                proof["prefix_sha256"] == prefix
                and result["seed"] == sel["banks"]["lru"]["ordered_keys"],
                "seal",
            )
        else:
            path = root / "ON/raw/events.pfj"
            need(
                SRC["digest"](path) == R["get"](E / "layout.json")["arms"][tag]["journal_sha256"],
                "P97",
            )
            rows, _ = SRC["T"]["PFJ"]["read_journal"](path)
        binding = SRC["Q"]["bindings"](rows)
        init = sorted(
            [layer, s, e, g]
            for (layer, s), (e, g, state, pin) in binding.items()
            if state == 2 and not pin
        )
        tx = [[r.call, r.tile, r.layer, r.slot, r.gen, r.expert, r.a] for r in rows if r.kind == 11]
        if tag == "P106":
            result.update(initial=init, reservations=tx)
        else:
            need(
                (tx, init) == (result["reservations"], result["initial"]),
                "different ordering or primary",
            )
    return result


def main(a):
    if a.archive:
        data = observe(a.archive)
    else:
        data = json.loads(gzip.decompress(a.witness.read_bytes()))
    return assess(data), data


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    inputs = p.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--archive", type=Path)
    inputs.add_argument("--witness", type=Path)
    p.add_argument("--new-output-dir", type=Path, required=True)
    a = p.parse_args()
    out = a.new_output_dir
    out.mkdir(mode=0o700)
    try:
        result, witness = main(a)
        packed = out / "transactions.json.gz"
        packed.write_bytes(
            gzip.compress(json.dumps(witness, separators=(",", ":")).encode(), mtime=0)
        )
        report = dict(
            evidence="TRACE_DERIVED_CONDITIONAL",
            result=result,
            transactions_sha256=SRC["digest"](packed),
            source_sha256=SRC["digest"](HERE / "tier_bank.py"),
            protocol_sha256=SRC["digest"](HERE / "tier-bank.md"),
            previous_sha256=SRC["digest"](E / "bank.json"),
        )
        tmp = out / ".pending"
        tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        tmp.rename(out / "receipt.json")
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as exc:
        (out / "failure.json").write_text(
            json.dumps(dict(status="FAIL_PRESERVED", reason=repr(exc))) + "\n"
        )
        raise
    print(SRC["digest"](out / "receipt.json"))
