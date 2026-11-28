"""Price a finite retention witness together with qualified, empty CPU regions."""

import argparse
import gzip
import heapq
import json
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
INTERVAL = run_path(HERE / "intervals.py")
SRC, CC, B, RE, need, CAP = (INTERVAL[k] for k in ("SRC", "CC", "B", "RE", "need", "CAP"))
LOOKUP = RE["QUAL"] / (
    "packed_nvme_manifest/server_profile/verified_block/server_reserve/"
    "causal_server/http/kv_width/natural/cpu_attention/target/http/lookup"
)
EMPTY = run_path(LOOKUP / "empty.py")
METHOD = "a0ecdd77949c3b3f82ba8b21afa6bf77fee4465c62d49babe214f4f2e0af7af9"
PARENT = "fe40b730da54e0e675619ff947735b5618a66ec087ecb4b4dcf1dc5fa2210f15"
PLACEMENT = "ec8f017f4beabcea09c329a651c081d9bff33605a10f6659be4dc765d596e6b5"
EMPTY_RESULT = "254cd2134868c9184d84f22820b8d5d3f290657d4427a0049dc76cf9f96780b8"


def critical_path(inside, edges, service):
    graph, workers = inside[0] + edges[0], service[0]
    for i in range(1, len(service)):
        graph, workers = (
            inside[i] + max(graph + edges[i], workers),
            service[i] + max(graph, workers),
        )
    return (max(graph + edges[-1], workers) + 3) // 4


class Prices:
    """Marginal change of the full P106 first clock. SET is always paid."""

    def __init__(self, regs, chosen):
        self.chosen = chosen
        self.inputs, self.base, self.positions = {}, {}, {}
        for number, groups, edges in regs:
            if number > 46:
                continue
            inside = [4 * g.internal for g in groups]
            edges = [4 * e for e in edges]
            service = [self.group_price(g, set()) for g in groups]
            self.inputs[number] = groups, inside, edges, service
            self.base[number] = critical_path(inside, edges, service)
            for j, group in enumerate(groups):
                for job in group.jobs:
                    self.positions[job.expert] = number, j

    def group_price(self, group, toggled):
        return B["layer_fourths"](
            [
                job.set_ns
                + (0 if (job.expert in self.chosen) ^ (job.expert in toggled) else job.read_ns)
                for job in group.jobs
            ]
        )

    def delta(self, toggled):
        touched = defaultdict(set)
        for i in toggled:
            if i in self.positions:
                number, j = self.positions[i]
                touched[number].add(j)
        change = 0
        for number, indexes in touched.items():
            groups, inside, edges, service = self.inputs[number]
            updated = service.copy()
            for j in indexes:
                updated[j] = self.group_price(groups[j], toggled)
            change += critical_path(inside, edges, updated) - self.base[number]
        return change


def search(regs, starts, chosen, capacity):
    chosen = chosen.copy()
    masks = {e: (1 << e) - (1 << s) for e, s in starts.items()}
    changes = []
    for _ in range(24):
        prices = Prices(regs, chosen)
        diff = [0] * (max(starts) + 1)
        for end in chosen:
            diff[starts[end]] += 1
            diff[end] -= 1
        use, full = 0, 0
        for t, d in enumerate(diff):
            use += d
            need(0 <= use <= capacity, "interval occupancy")
            if use == capacity:
                full |= 1 << t
        delta = {i: prices.delta({i}) for i in starts}
        blocked = {i: masks[i] & full for i in starts if i not in chosen}
        candidates = (
            (delta[add] + delta[drop], drop, add)
            for add, conflict in blocked.items()
            for drop in chosen
            if conflict & ~masks[drop] == 0
        )
        top = heapq.nsmallest(12, candidates)
        if not top:
            break
        actual, drop, add = min((prices.delta({drop, add}), drop, add) for _, drop, add in top)
        if actual >= 0:
            break
        chosen.remove(drop)
        chosen.add(add)
        changes.append([drop, add, actual])
    return chosen, changes


def placements(path):
    receipt = SRC["pinned"](path / "receipt.json", PLACEMENT)
    need(receipt["status"] == "MEASURED_RESERVED_GRAPHS", "placement authority")
    local = set()
    for case in receipt["cases"]:
        regions = SRC["pinned"](path / ("regions-" + case["file"]), case["audit_sha256"])
        need(regions["tokens"] == case["tokens"] and regions["outputs"] == 1, "shape")
        for row in regions["regions"]:
            if row["status"] == "LOCAL_CPU":
                local.add((case["tokens"], row["layer"], row["wave"]))
    need(len(local) == 264, "placement census")
    return local


def graph_credits(rows, local, frozen):
    waves, _ = SRC["timeline"](rows)
    host = SRC["NATIVE"]["host_trace"](rows)
    ranks, sites = defaultdict(Counter), defaultdict(list)
    for e in rows:
        if e.call <= 2 and e.kind == 27:
            ranks[e.call, e.tile, e.layer].update(e.a.to_bytes(4, "little"))
    for w in waves:
        if w.site[0] <= 2:
            sites[w.site[:3]].append(w)
    sizes = {}
    for site, ws in sites.items():
        demand_sets = [{k[3] for k in w.demands} for w in ws]
        sizes.update(
            (w.site, n)
            for w, n in zip(ws, EMPTY["rank_counts"](demand_sets, ranks[site]), strict=True)
        )
    detail = {name: Counter() for name in ("any_cpu", "placed")}
    credits = {name: defaultdict(Counter) for name in detail}
    for call in host["calls"][:2]:
        ws = [w for w in waves if w.site[0] == call["number"]]
        gaps = EMPTY["following"]([(w.start, w.end) for w in ws], call["return_ns"])
        for i, (w, gap) in enumerate(zip(ws, gaps, strict=True)):
            site = w.site[:3]
            if site[2] >= 25 or sizes[w.site]:
                continue
            need(not w.reserved, "an empty region retained routed work")
            n, rem = divmod(sum(ranks[site].values()), 4)
            need(not rem and n in (32, 20), "empty CPU shape")
            side = "inside" if i + 1 < len(ws) and ws[i + 1].site[:3] == site else "edge"
            for name in detail:
                if name == "any_cpu" or (n, site[2], w.site[3]) in local:
                    detail[name]["waves"] += 1
                    detail[name][side + "_ns"] += gap
                    credits[name][site][side] += gap
    all_cpu = detail["any_cpu"]
    need(
        all_cpu["waves"] == 739
        and all_cpu["inside_ns"] + all_cpu["edge_ns"] == frozen["gap_after_empty_ns"]["CPU"],
        "historical empty wave conservation",
    )
    return credits, detail


def discount(data, credits):
    result = {}
    for label, (regs, outside) in data.items():
        used = set()
        updated = []
        for number, groups, edges in regs:
            new_groups, new_edges = [], edges.copy()
            for i, g in enumerate(groups):
                c = credits[label].get(g.site, {})
                internal = g.internal - c.get("inside", 0)
                new_edges[i + 1] -= c.get("edge", 0)
                need(internal >= 0 and new_edges[i + 1] >= 0, "double counted graph time")
                new_groups.append(RE["Region"](g.site, internal, g.jobs))
                if c:
                    used.add(g.site)
            updated.append((number, new_groups, new_edges))
        need(used == credits[label].keys(), "unmatched placement")
        result[label] = updated, outside
    return result


def run(a):
    need(SRC["digest"](HERE / "composition.md") == METHOD, "method")
    parent = SRC["pinned"](a.intervals / "receipt.json", PARENT)
    proof_path = a.intervals / "schedule.json.gz"
    need(SRC["digest"](proof_path) == parent["schedule_sha256"], "parent assignments")
    proof = json.loads(gzip.decompress(proof_path.read_bytes()))
    previous = SRC["pinned"](LOOKUP / "empty-result.json", EMPTY_RESULT)
    prior = SRC["pinned"](B["NATURAL"] / "prefill_retention/request_cost/receipt.json", B["PRIOR"])
    local = placements(a.placement)
    root = a.archive / "part-106" / SRC["SOURCES"]["P106"][0]
    seal, rows106, _, _ = SRC["Q"]["read_new"](root, SRC["SOURCES"]["P106"][1])
    seed = list(map(tuple, seal["banks"]["lru"]["ordered_keys"]))
    data, credits, graph = {}, defaultdict(dict), {}
    for label in ("P106", "P97"):
        rows = rows106
        if label == "P97":
            path = a.archive / "part-97" / SRC["SOURCES"][label][0] / "ON/raw/events.pfj"
            rows, _ = SRC["T"]["PFJ"]["read_journal"](path)
        data[label], tx, primary, prices, _, lineage = INTERVAL["load_arm"](
            a.archive, label, rows, seed, prior[label]
        )
        need(list(lineage) == parent["routing_and_reservations"], "route or transaction order")
        by_mode, graph[label] = graph_credits(rows, local, previous["journals"][label])
        for name, c in by_mode.items():
            credits[name][label] = c
    seed = [key for key in seed if key not in primary]
    starts = INTERVAL["opportunities"](tx, seed)
    eligible = {i: s for i, s in starts.items() if i in prices}
    policies = {
        name: {i for _, i, _ in proof[name]} for name in ("recent", "frequency", "price_oracle")
    }
    chosen = policies["price_oracle"]
    if a.verify:
        witness = json.loads(a.verify.read_bytes())
        changes = witness["exchanges"]
        chosen = chosen.copy()
        for drop, add, delta in changes:
            need(drop in chosen and add not in chosen and add in eligible and delta < 0, "exchange")
            chosen.remove(drop)
            chosen.add(add)
    else:
        chosen, changes = search(data["P106"][0], eligible, chosen, CAP)
    slots, peak = INTERVAL["assign"](eligible, chosen, CAP)
    volume = INTERVAL["audit"](tx, seed, eligible, slots, CAP)
    candidate = {
        "exchanges": changes,
        "intervals": [[starts[i], i, slots[i]] for i in sorted(chosen)],
    }
    if a.verify:
        need(witness == candidate, "witness content or slot allocation")
    policies["critical_oracle"] = chosen
    zero = discount(data, {label: {} for label in data})
    domains = {"unchanged": zero, **{k: discount(data, v) for k, v in credits.items()}}
    result = {}
    for policy, ids in policies.items():
        result[policy] = {
            graph_mode: {m: CC["assess"](regs, ids, m == "direct") for m in ("copied", "direct")}
            for graph_mode, regs in domains.items()
        }
        if policy in parent["results"]:
            need(
                result[policy]["unchanged"] == parent["results"][policy]["clocks"], "normalization"
            )
    original = result["price_oracle"]["unchanged"]["copied"]["with_full_client_cost_ns"]
    final = result["critical_oracle"]["unchanged"]["copied"]["with_full_client_cost_ns"]
    need(
        original["P106"]["first_final"] + sum(d for _, _, d in changes)
        == final["P106"]["first_final"],
        "exchange pricing",
    )
    dst = a.new_output_dir / "witness.json"
    dst.write_text(json.dumps(candidate, separators=(",", ":")) + "\n")
    return {
        "status": "TRACE_DERIVED",
        "schema": "tesy.ready_bank_composition.v1",
        "method_sha256": METHOD,
        "source_sha256": SRC["digest"](Path(__file__)),
        "intervals_sha256": PARENT,
        "placement_sha256": PLACEMENT,
        "empty_sha256": EMPTY_RESULT,
        "exchanges": len(changes),
        "peak": peak,
        "payload_bytes_per_expert": RE["PAYLOAD"],
        "critical_counts_by_tier": volume,
        "witness_sha256": SRC["digest"](dst),
        "empty_graph": graph,
        "results": result,
        "decisions": {
            "finite_selection_paid_set": "HEADROOM_ONLY"
            if all(B["joint"](c) >= 0 for c in final.values())
            else "INCONCLUSIVE",
            "placed_plus_causal": {
                p: "HEADROOM_ONLY" if result[p]["placed"]["direct"]["fits_with_grant"] else "NO_GO"
                for p in ("recent", "frequency")
            },
        },
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("archive", "intervals", "placement", "new-output-dir"):
        p.add_argument("--" + arg, type=Path, required=True)
    p.add_argument("--verify", type=Path)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        res = run(a)
    except FileNotFoundError as e:
        path = Path(e.filename).resolve()
        raw = path.is_relative_to(a.archive.resolve()) or path.is_relative_to(a.placement.resolve())
        res = {"status": "NOT_RUN_RAW_REQUIRED" if raw else "FAIL", "missing": path.name}
    except (ValueError, AssertionError, KeyError, TypeError, OSError) as e:
        res = {"status": "FAIL", "reason": str(e)}
    tmp = a.new_output_dir / ".pending"
    tmp.write_text(json.dumps(res, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    print(res["status"], res.get("decisions", res.get("reason", "")))
    raise SystemExit(res["status"] != "TRACE_DERIVED")
