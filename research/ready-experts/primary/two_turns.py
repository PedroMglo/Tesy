"""Seal primary and secondary contents from T1, then evaluate T2 against both laptop clocks."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from runpy import run_path
from types import FunctionType, MethodType

HERE = Path(__file__).resolve().parent
P = run_path(HERE / "replay.py")
SRC, R, RE, IV, B, CC, CO, need = (P[k] for k in ("SRC", "R", "RE", "IV", "B", "CC", "CO", "need"))
PROFILE = run_path(HERE.parent / "selection.py")
METHOD = "08c1636ca48c1e6cdd53f6b1cc3f58b4d5c07de001911c83934b5ff2d057cc38"
PARENT = "f1ae0a26073dbf74eba9e10a204d28b2a41abfd42ddeeac367881bf6f63a70c1"
SLOTS, LAYERS, EXPERTS = 40, 36, 128


class History:
    """Ranks in one routed tile count as one reference, irrespective of wave or multiplicity."""

    def __init__(self):
        self.epoch = [0] * LAYERS
        self.last = [[0] * EXPERTS for _ in self.epoch]
        self.previous = [[0] * EXPERTS for _ in self.epoch]

    def visit(self, layer, ranks):
        self.epoch[layer] += 1
        for e in set(ranks):
            self.previous[layer][e] = self.last[layer][e]
            self.last[layer][e] = self.epoch[layer]

    def choose(self, layer, k, pool, keep, tagged):
        free = [s for s, e in enumerate(pool.ids) if s not in keep]
        if not free:
            raise R["OrderUnknown"]("no unpinned slot")
        empty = [s for s in free if pool.ids[s] < 0]
        if empty:
            return empty[0]
        choices = [s for s in free if pool.ids[s] in tagged] or free
        last, before = self.last[layer], self.previous[layer]
        return min(
            choices, key=lambda s: (before[pool.ids[s]] if k == 2 else 0, last[pool.ids[s]], s)
        )


def words_zero():
    # Test policies use neither the unobserved native ages nor its heat as a tiebreaker.
    return [[0] * 169 for _ in range(LAYERS)]


def with_policy(slots, hist, k, tags):
    manager = R["Manager"](slots, words_zero(), 0, 2304, tags)
    layer_ids = {id(p): n for n, p in enumerate(manager.pools)}

    def select(pool, keep, tagged):
        return hist.choose(layer_ids[id(pool)], k, pool, keep, tagged)

    # Reuse the frozen callback including pins, next-wave reads and parking. The copy has
    # a private name binding for victim(); independent instances never patch the control.
    original = R["Manager"].callback
    callback = FunctionType(original.__code__, {**original.__globals__, "victim": select})
    manager.callback = MethodType(callback, manager)
    return manager


def snapshot(manager):
    R["clone"](manager, manager.bank)  # all generations drained at the cut
    return [
        (e, gen, 2 if e >= 0 else 0, 0)
        for pool in manager.pools
        for e, gen in zip(pool.ids, pool.gen, strict=True)
    ]


class FirstTurn:
    def __init__(self):
        self.held = {}
        self.training = Counter()
        self.traffic = defaultdict(Counter)

    def reserve(self, call, layer, expert, old):
        key = layer, expert
        self.training[key] += 1
        phase = "prefill" if call <= 9 else "decode"
        c = self.traffic[phase, IV["by_tier"](key)]
        c["read_windows"] += 1
        if old < 0:
            return
        key = (layer, old)
        c["victim_offers"] += 1
        if key in self.held:
            del self.held[key]
        else:
            c["captured_payloads"] += 1
        self.held[key] = None
        if len(self.held) > P["CAP"]:
            del self.held[next(iter(self.held))]

    def freeze(self, slots):
        need(
            len(self.held) == P["CAP"] and all(s[2:] == (2, 0) for s in slots), "T1 seal not ready"
        )
        data = {}
        for (phase, tier), c in self.traffic.items():
            data.setdefault(phase, {})[tier] = {
                **c,
                "requested_bytes": c["read_windows"] * RE["WINDOW"],
                "captured_payload_bytes": c["captured_payloads"] * P["PAYLOAD"],
            }
        return dict(
            slots=slots, seed=list(self.held), training=sorted(self.training.items()), traffic=data
        )


def t1_plan(arm):
    need(SRC["digest"](HERE / "turns.md") == METHOD, "protocol")
    before = SRC["pinned"](arm / "before-t2.json", PROFILE["T1_SEAL"])
    pf = PROFILE["PROFILE"]
    rows = list(pf["iter_rows"](arm / "observer/events.pfj", 0, before["records"]))
    grade, _ = pf["prefix_grade"](rows, pf["T1"], 9)
    need(all(before[k] == v for k, v in grade.items()) and len(rows) == 87736, "T1 prefix")
    initial = [None] * (LAYERS * SLOTS)
    real = FirstTurn()
    ranks = defaultdict(list)
    for e in rows:
        if e.kind == 5:
            initial[e.layer * SLOTS + e.slot] = (e.expert, e.gen, e.a, e.b)
        elif e.kind == 27:
            ranks[e.call, e.tile, e.layer].extend(e.a.to_bytes(4, "little"))
        elif e.kind == 11:
            real.reserve(e.call, e.layer, e.expert, e.a)
    need(
        sum(s[2] == 2 for s in initial) == 261 and sum(map(len, ranks.values())) == 74278 * 4,
        "initial warm slots or quartet count",
    )
    native = initial.copy()
    for e in rows:
        if e.kind == 17:
            native[e.layer * SLOTS + e.slot] = (e.expert, e.gen, 2, 0)
    arms = {"native": real.freeze(native)}
    history = History()
    for (_, _, layer), ids in ranks.items():
        history.visit(layer, ids)
    for k in (1, 2):
        h = History()
        manager = with_policy(initial, h, k, [set() for _ in range(LAYERS)])
        bank = FirstTurn()
        for (call, _, layer), ids in ranks.items():
            h.visit(layer, ids)
            waves = range((min(128, len(ids)) + 17) // 18) if len(ids) > SLOTS else [-1]
            for wave in waves:
                alloc, _ = manager.callback(layer, wave, ids)
                for e, _, _, old, _ in alloc:
                    bank.reserve(call, layer, e, old)
        arms["k" + str(k)] = bank.freeze(snapshot(manager))
        need(vars(h) == vars(history), "history changes with slot assignment")
    return dict(
        schema="tesy.two_turn_residency_plan.v1",
        status="SEALED_BEFORE_T2",
        method_sha256=METHOD,
        prefix_sha256=grade["sha256"],
        history=vars(history),
        arms=arms,
    )


def suffix(groups, slots, tags, old_history, k):
    h = History()
    for name, value in old_history.items():
        setattr(h, name, [x.copy() if isinstance(x, list) else x for x in value])
    manager = with_policy(slots, h, k, tags)
    first, jobs = {}, []
    for group in groups:
        site = group["site"]
        _, _, layer, wave = site
        if wave in (-1, 0):
            ranks = group["ranks"]
            h.visit(layer, ranks)
        added, demanded = manager.callback(layer, wave, ranks)
        need([e for e, _, _ in demanded] == [x[0] for x in group["demands"]], "route changed in T2")
        for e, slot, gen, old, reason in added:
            jobs.append((site, (layer, slot, gen, e), old, reason))
        for e, slot, gen in demanded:
            first.setdefault((layer, slot, gen, e), site)
    end = snapshot(manager)
    resolved = [P["Load"](site, key, old, reason, first[key]) for site, key, old, reason in jobs]
    need(
        len({j.match for j in resolved}) == len(jobs)
        and all(j.site[:3] == j.deadline[:3] for j in resolved),
        "unmatched first consumer",
    )
    return resolved, IV["digest"](end)


def timings(data, template, exterior, credits, jobs, lookup, hits):
    results = {}
    for mode in ("same_slot_gen", "same_expert"):
        raw = {}
        for label, costs in data.items():
            priced, ur, us = P["priced"](jobs, lookup, costs, exact_slot=mode == "same_slot_gen")
            raw[label] = P["inject"](template[label], priced), exterior[label]
        result = {"unpriced": {"READ_nonhit": len(ur - hits), "SET_generations": len(us)}}
        for g, d in (("unchanged", raw), ("placed", CO["discount"](raw, credits))):
            result[g] = {m: CC["assess"](d, hits, m == "direct") for m in ("direct", "copied")}
            if g == "placed" and mode == "same_slot_gen":
                # The old budget routine charges copied hits. Set the hit SETs to zero to
                # reproduce the favourable direct path throughout the bracket search.
                direct = {}
                for label, (regions, outside) in d.items():
                    new = [
                        (
                            n,
                            [
                                RE["Region"](
                                    x.site,
                                    x.internal,
                                    [
                                        RE["Job"](
                                            j.expert, j.read_ns, 0 if j.expert in hits else j.set_ns
                                        )
                                        for j in x.jobs
                                    ],
                                )
                                for x in gs
                            ],
                            edges,
                        )
                        for n, gs, edges in regions
                    ]
                    direct[label] = new, outside
                need(CC["assess"](direct, hits, False) == result[g]["direct"], "direct price")
                result[g]["budget"] = P["unknown_budget"](direct, hits, ur)
        results[mode] = result
    return results


def score(a):
    parent = SRC["pinned"](HERE / "evidence/receipt.json", PARENT)
    plan = SRC["pinned"](a.plan, a.plan_sha256)
    root = a.archive / "part-106" / SRC["SOURCES"]["P106"][0]
    # Only the bounded prefix is read before verifying this plan.
    need(plan == json.loads(json.dumps(t1_plan(root / "ON"))), "changed sealed T1 plan")
    h = SRC["pinned"](RE["EXCLUSIVE"].parent / "replay/evidence/receipt.json", P["HIST"])
    path = a.archive / "part-63/tesy-policy-natural-physical-20261125-r02"
    raw, states, words, calls, interval, _, _, _ = R["sources"](path, h["family_receipt_sha256"])
    groups = R["segment"](raw)[0]
    start = groups[0]["site"][0]
    for g in groups:
        call, *site = g["site"]
        g["site"] = (call - start + 1, *site)
    blank = [set() for _ in range(LAYERS)]
    orig = P["reconstruct"](groups, states, words, calls, interval, blank, h["r0"], control=True)[0]
    lookup = {j.match: j for j in orig}
    plan0 = plan["arms"]["native"]
    sealed, t2, _, _ = SRC["Q"]["read_new"](root, SRC["SOURCES"]["P106"][1])
    need(
        sealed["banks"]["lru"]["ordered_keys"] == plan0["seed"]
        and list(map(tuple, plan0["slots"])) == states,
        "different initial candidates or owners",
    )
    base = SRC["pinned"](B["NATURAL"] / "prefill_retention/request_cost/receipt.json", B["PRIOR"])
    placements = CO["placements"](a.placement)
    gaps = SRC["pinned"](CO["LOOKUP"] / "empty-result.json", CO["EMPTY_RESULT"])
    data, template, exterior, credits = {}, {}, {}, {}
    for label in ("P106", "P97"):
        (_, _, _), auth = B["read_arm"](a.archive, label, base[label])
        rows = t2
        if label == "P97":
            path = a.archive / "part-97" / SRC["SOURCES"][label][0] / "ON/raw/events.pfj"
            rows, _ = SRC["T"]["PFJ"]["read_journal"](path)
        gs, data[label] = P["packed_groups"](rows)
        need(gs == groups, "different T2")
        waves, _ = SRC["timeline"](rows)
        template[label] = list(
            IV["C"]["partition"](
                SRC["NATIVE"]["host_trace"](rows)["calls"], waves, defaultdict(dict)
            )
        )
        exterior[label] = auth["outside_calls_ns"]
        credits[label] = CO["graph_credits"](rows, placements, gaps["journals"][label])[0]["placed"]
    results = {}
    initial0 = {(i // SLOTS, s[0]) for i, s in enumerate(states)}
    for t1, t2k in (("native", 0), ("native", 2), ("k1", 1), ("k2", 2)):
        trained = plan["arms"][t1]
        slots = list(map(tuple, trained["slots"]))
        initial = {(i // SLOTS, s[0]) for i, s in enumerate(slots)}
        seed = list(map(tuple, trained["seed"]))
        tags = [{e for layer, e in seed if layer == n} for n in range(LAYERS)]
        training = Counter({tuple(key): count for key, count in trained["training"]})
        if t2k:
            jobs, end = suffix(groups, slots, tags, plan["history"], t2k)
        else:
            jobs = P["reconstruct"](
                groups, states, words, calls, interval, tags, h["carry"], control=False
            )[0]
            end = None
        hits, _, traffic = P["sources"](jobs, initial, seed, training, "frequency")
        cold = P["cold_sites"](groups, initial | set(seed))
        P["first_acquisitions"](jobs, cold)
        clocks = timings(data, template, exterior, credits, jobs, lookup, hits)
        if not t2k:
            control = parent["policies"]["tagged_frequency"]
            need(
                control["by_phase_tier"] == traffic
                and all(
                    clocks[m][g][s] == control["clocks"][m][g][s]
                    for m in clocks
                    for g in ("placed", "unchanged")
                    for s in ("copied", "direct")
                ),
                "control changed",
            )
        fav = clocks["same_slot_gen"]["placed"]["direct"]
        results[t1 + "_" + ("k" + str(t2k) if t2k else "native")] = dict(
            t1=trained["traffic"],
            primary_entry_changed=len(initial - initial0),
            seed_difference=len(set(seed) - set(map(tuple, plan0["seed"]))),
            primary_seed_overlap=len(set(seed) & initial),
            reservations=len(jobs),
            disk=len(jobs) - len(hits),
            compulsory=len(cold),
            compulsory_by_phase=dict(Counter(B["phase"](site[0]) for site in cold.values())),
            t2=traffic,
            clocks=clocks,
            ending_bindings_sha256=end,
            decision=("INCONCLUSIVE_SERVICE_REQUIRED" if fav["fits_with_grant"] else "NO_GO"),
        )
    return dict(
        schema="tesy.two_turn_residency.v1",
        status="TRACE_DERIVED",
        method_sha256=METHOD,
        parent_sha256=PARENT,
        source_sha256=SRC["digest"](Path(__file__)),
        plan_sha256=a.plan_sha256,
        prefix_sha256=plan["prefix_sha256"],
        arms=results,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="action", required=True)
    train = sub.add_parser("train")
    train.add_argument("--t1-arm", required=True, type=Path)
    grade = sub.add_parser("score")
    for name in ("archive", "placement", "plan"):
        grade.add_argument("--" + name, required=True, type=Path)
    grade.add_argument("--plan-sha256", required=True)
    for cmd in (train, grade):
        cmd.add_argument("--new-output-dir", required=True, type=Path)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = t1_plan(a.t1_arm) if a.action == "train" else score(a)
    except FileNotFoundError as e:
        roots = [getattr(a, k, None) for k in ("archive", "placement", "t1_arm")]
        raw = any(
            root and Path(e.filename).resolve().is_relative_to(root.resolve()) for root in roots
        )
        result = {
            "status": "NOT_RUN_RAW_REQUIRED" if raw else "FAIL",
            "missing": Path(e.filename).name,
        }
    except (ValueError, KeyError, OSError, TypeError, AssertionError, R["OrderUnknown"]) as e:
        result = {
            "status": "INCONCLUSIVE" if isinstance(e, R["OrderUnknown"]) else "FAIL",
            "reason": str(e),
        }
    tmp = a.new_output_dir / ".pending"
    tmp.write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    )
    tmp.rename(a.new_output_dir / ("plan.json" if a.action == "train" else "receipt.json"))
    print(result["status"], result.get("reason", ""))
    return result["status"] not in ("SEALED_BEFORE_T2", "TRACE_DERIVED")


if __name__ == "__main__":
    raise SystemExit(main())
