"""Compare primary victims using the same routes, checked deadlines and per-process prices."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
D = run_path(HERE.parent / "renewal/deadlines.py")
IV, RE, SRC, B, CC, CO, need = (D[k] for k in ("IV", "RE", "SRC", "B", "CC", "CO", "need"))
R = run_path(RE["EXCLUSIVE"].parent / "replay/screen.py")
CAP, PAYLOAD = IV["CAP"], IV["PAYLOAD"]
METHOD = "16df0b36a91a9a71bf4872bf588e9217b8d9de9df07bfb53f658c1fca92700f4"
DECISION = "314db3ad9f772e3e1d8d564259cbcccc29d93c79123d5f6cf41f47b4e3a8970d"
HIST = "494bb5d2e73b4e129b020118e1bcf2110f253b1c2b565b5d110023129516aa54"


@dataclass(frozen=True)
class Load:
    site: tuple
    key: tuple
    victim: int
    reason: int
    deadline: tuple

    @property
    def expert(self):
        return self.key[0], self.key[3]

    @property
    def match(self):
        return self.site, self.deadline, self.expert


def packed_groups(rows):
    groups, prices = [], {}
    for e in rows:
        key = SRC["key"](e)
        if e.kind == 9:
            group = dict(site=SRC["origin"](e), rows=e.a, ranks=[], new=[], demands=[])
            groups.append(group)
        elif e.kind == 27:
            group["ranks"].extend(e.a.to_bytes(4, "little"))
        elif e.kind == 10:
            group["demands"].append((e.expert, e.slot, e.gen))
        elif e.kind == 11:
            group["new"].append((e.expert, e.slot, e.gen, e.a))
        elif e.kind == 12 and e.a != 1:
            pending = group["new"][-1]
            need(
                len(pending) == 4 and pending[:3] == (e.expert, e.slot, e.gen) and e.a in (0, 2),
                "reserve reason",
            )
            group["new"][-1] = (*pending, e.a)
        elif e.kind == 30:
            need(key not in prices and e.b == e.c == RE["WINDOW"] and not e.error, "packed READ")
            prices[key] = [e.ns - e.begin]
        elif e.kind == 16:
            need(e.component == len(prices[key]) - 1 < 3 and e.a * 3 == PAYLOAD, "SET component")
            prices[key].append(e.ns - e.begin)
    need(
        len(prices) == 2354 and all(len(v) == 4 and min(v) >= 0 for v in prices.values()),
        "three SET per READ",
    )
    return groups, {k: (v[0], sum(v[1:])) for k, v in prices.items()}


def reconstruct(groups, slots, words, calls, interval, tags, expected, *, control):
    m = R["Manager"](slots, words, calls, interval, tags)
    releases, first = [], {}
    cut = None
    ranks = None
    for g in groups:
        site = g["site"]
        call, _, layer, wave = site
        if call == 3 and cut is None:
            cut = R["clone"](m, tags)
        if wave in (-1, 0):
            ranks = g["ranks"]
        need(len(ranks) == 4 * g["rows"], "rank geometry")
        alloc, demanded = m.callback(layer, wave, ranks)
        need(
            [r[0] for r in demanded] == [r[0] for r in g["demands"]], "changed authoritative demand"
        )
        if control:
            need(alloc == g["new"] and demanded == g["demands"], "reference slot or reservation")
        for e, s, gen, old, reason in alloc:
            releases.append((site, (layer, s, gen, e), old, reason))
        for e, s, gen in demanded:
            first.setdefault((layer, s, gen, e), site)
    need(
        m.emitted.hexdigest() == expected["inferred_slot_stream_sha256"]
        and dict(m.proofs) == expected["induction"],
        "historical parking and reference trajectory",
    )
    R["clone"](m, tags)  # Asserts the end-of-request drain in the manager.
    jobs = [Load(site, k, old, reason, first[k]) for site, k, old, reason in releases]
    need(
        len({j.match for j in jobs}) == len(jobs)
        and all(j.site[:3] == j.deadline[:3] for j in jobs),
        "ambiguous transport site or consumer in another region",
    )
    return jobs, cut


def cold_sites(groups, initial):
    """No eviction choice can make an exact, previously unseen weight available any earlier."""
    seen = initial.copy()
    cold = {}
    for g in groups:
        call, tile, layer, wave = g["site"]
        if wave not in (-1, 0):
            continue
        for expert in g["ranks"]:
            key = (layer, expert)
            if key not in seen:
                cold[key] = (call, tile, layer)
                seen.add(key)
    return cold


def first_acquisitions(jobs, cold):
    found = {}
    for i, j in enumerate(jobs, 1):
        if j.expert in cold and j.expert not in found:
            need(j.site[:3] == j.deadline[:3] == cold[j.expert], "first-acquisition locality")
            found[j.expert] = i
    need(cold.keys() == found.keys(), "missing cold weights")
    return found


def sources(jobs, initial, seed, counts, mode):
    # The primary manager has already chosen and proven every victim. Secondary admission is causal.
    held = {
        k: (counts[k] if mode == "frequency" else 0, i - len(seed))
        for i, k in enumerate(seed)
        if mode == "fixed" or k not in initial
    }
    freq = counts.copy()
    hits, traffic = set(), defaultdict(Counter)
    cut = None
    for i, j in enumerate(jobs, 1):
        phase = B["phase"](j.site[0])
        key = j.expert
        if j.site[0] >= 3 and cut is None:
            cut = set(held)
        c = traffic[(phase, IV["by_tier"](key))]
        c["reservations"] += 1
        if key in held:
            hits.add(i)
            c["hits"] += 1
        if mode == "fixed":
            continue
        held.pop(key, None)
        if mode == "frequency":
            freq[key] += 1
        old = (key[0], j.victim)
        need(j.victim >= 0 and old not in held, "duplicate or absent victim")
        held[old] = (freq[old] if mode == "frequency" else 0, i)
        if len(held) > CAP:
            del held[min(held, key=held.__getitem__)]
        c["captures"] += old in held
    summary = {}
    for (phase, tier), c in traffic.items():
        c["disk_windows"] = c["reservations"] - c["hits"]
        c["disk_requested_bytes"] = c["disk_windows"] * RE["WINDOW"]
        c["capture_payload_bytes"] = c["captures"] * PAYLOAD
        c["hit_payload_bytes"] = c["hits"] * PAYLOAD
        summary.setdefault(phase, {})[tier] = dict(c)
    need(cut is not None and len(held) <= CAP, "secondary capacity or missing decode")
    return hits, cut, summary


def different(ref, alt):
    out = defaultdict(Counter)
    for name, rows in (
        ("removed", ref.keys() - alt.keys()),
        ("new", alt.keys() - ref.keys()),
        ("shared", ref.keys() & alt.keys()),
    ):
        for site, _, key in rows:
            out[B["phase"](site[0]), IV["by_tier"](key)][name] += 1
    result = {}
    for (phase, tier), c in out.items():
        result.setdefault(phase, {})[tier] = dict(c)
    return result


def priced(jobs, ref, costs, *, exact_slot):
    regions = defaultdict(list)
    missing_read, missing_set = set(), set()
    for i, j in enumerate(jobs, 1):
        r = ref.get(j.match)
        read, copy = (0, 0) if r is None else costs[r.key]
        if r is None:
            missing_read.add(i)
        if r is None or (exact_slot and r.key != j.key):
            copy = 0
            missing_set.add(i)
        regions[j.site[:3]].append(RE["Job"](i, read, copy))
    return regions, missing_read, missing_set


def inject(template, jobs):
    seen = set()
    data = []
    for n, regions, edges in template:
        new = []
        for g in regions:
            new.append(RE["Region"](g.site, g.internal, jobs.get(g.site, [])))
            seen.add(g.site)
        data.append((n, new, edges))
    need(jobs.keys() <= seen, "orphaned transport")
    return data


def unknown_budget(data, hits, unknown):
    def assess(ns):
        updated = {}
        for label, (regs, out) in data.items():
            rows = []
            for n, gs, edges in regs:
                new = []
                for g in gs:
                    js = [
                        RE["Job"](j.expert, ns if j.expert in unknown else j.read_ns, j.set_ns)
                        for j in g.jobs
                    ]
                    new.append(RE["Region"](g.site, g.internal, js))
                rows.append((n, new, edges))
            updated[label] = (rows, out)
        return CC["assess"](updated, hits, False)

    zero = CC["assess"](data, hits, False)
    output = {}
    for clock, passes in (
        ("full_client", D["fits"]),
        ("p106_grant", lambda row: row["fits_with_grant"]),
    ):
        if not passes(zero):
            output[clock] = {"status": "MISSES_AT_ZERO"}
        elif not unknown - hits:
            output[clock] = {"status": "NO_UNKNOWN_READ"}
        else:
            lo, hi = 0, 12_000_000_000
            need(not passes(assess(hi)), "no upper bracket")
            while hi - lo > 1:
                mid = (hi + lo) // 2
                if passes(assess(mid)):
                    lo = mid
                else:
                    hi = mid
            output[clock] = {"max_ns_per_unknown_read": lo, "first_failing_ns_per_unknown_read": hi}
    return output


def run(a):
    need(SRC["digest"](HERE / "protocol.md") == METHOD, "frozen method")
    prev = SRC["pinned"](HERE.parent / "renewal/evidence/decision.json", DECISION)
    history = SRC["pinned"](RE["EXCLUSIVE"].parent / "replay/evidence/receipt.json", HIST)
    family = a.archive / "part-63/tesy-policy-natural-physical-20261125-r02"
    raw, slots, words, calls, interval, tags, bases, origin = R["sources"](
        family, history["family_receipt_sha256"]
    )
    groups, _, work = R["segment"](raw)
    start = groups[0]["site"][0]
    for g in groups:
        c, *tail = g["site"]
        g["site"] = (c - start + 1, *tail)
    need(work == history["observed"], "P63 population")
    blank = [set() for _ in range(36)]
    first_primary, cut0 = reconstruct(
        groups, slots, words, calls, interval, blank, history["r0"], control=True
    )
    alt, cut1 = reconstruct(
        groups, slots, words, calls, interval, tags, history["carry"], control=False
    )
    ref = {j.match: j for j in first_primary}
    initial = {(i // 40, r[0]) for i, r in enumerate(slots) if r[0] >= 0}
    need(len(groups) == 2987 and len(initial) == 1440 and len(ref) == 2354, "R0 geometry")
    basecost = SRC["pinned"](
        B["NATURAL"] / "prefill_retention/request_cost/receipt.json", B["PRIOR"]
    )
    gaps = SRC["pinned"](CO["LOOKUP"] / "empty-result.json", CO["EMPTY_RESULT"])
    placements = CO["placements"](a.placement)
    root = a.archive / "part-106" / SRC["SOURCES"]["P106"][0]
    seal, rows106, _, _ = SRC["Q"]["read_new"](root, SRC["SOURCES"]["P106"][1])
    seed = list(map(tuple, seal["banks"]["lru"]["ordered_keys"]))
    need(
        set(seed) == {(layer, e) for layer, keys in enumerate(tags) for e in keys},
        "different sealed LRU",
    )
    training, t1 = IV["train"](root / "ON")
    need(t1 == prev["t1"]["t1_prefix_sha256"], "frequency training changed")
    templates, exterior, prices, credits = {}, {}, {}, {}
    want = {(i // 40, i % 40): tuple(r) for i, r in enumerate(slots)}
    for label in ("P106", "P97"):
        (_, _, _), auth = B["read_arm"](a.archive, label, basecost[label])
        rows = rows106
        if label == "P97":
            raw_path = a.archive / "part-97" / SRC["SOURCES"][label][0] / "ON/raw/events.pfj"
            rows, _ = SRC["T"]["PFJ"]["read_journal"](raw_path)
        observed, prices[label] = packed_groups(rows)
        need(
            observed == groups
            and SRC["Q"]["bindings"](rows) == want
            and auth["trajectory_sha256"] == prev["routing_and_reservations"][0],
            "P63/P97/P106 control disagreement",
        )
        waves, _ = SRC["timeline"](rows)
        templates[label] = list(
            IV["C"]["partition"](
                SRC["NATIVE"]["host_trace"](rows)["calls"], waves, defaultdict(dict)
            )
        )
        exterior[label] = auth["outside_calls_ns"]
        c, detail = CO["graph_credits"](rows, placements, gaps["journals"][label])
        need(detail == prev["request"]["eligible_empty_cpu"][label], "parking credit")
        credits[label] = c["placed"]
    cold = cold_sites(groups, initial | set(seed))
    refc = first_acquisitions(first_primary, cold)
    first_acquisitions(alt, cold)
    force = {}
    for pay in ("read_only", "read_and_set"):
        data = {}
        for label, template in templates.items():
            charges = defaultdict(list)
            for i in refc.values():
                j = first_primary[i - 1]
                read, copy = prices[label][j.key]
                charges[j.site[:3]].append(RE["Job"](i, read, copy if pay == "read_and_set" else 0))
            data[label] = inject(template, charges), exterior[label]
        force[pay] = {
            g: CC["assess"](regs, set(), False)
            for g, regs in (("unchanged", data), ("placed", CO["discount"](data, credits)))
        }
    for g, v in force["read_and_set"].items():
        need(
            v["with_full_client_cost_ns"]
            == prev["request"]["full_client_and_decode_ns"]["unlimited"][g]["direct"],
            "independent first-use bound differs",
        )
    policies = {}
    ref_misses = {}
    for name, jobs in (("r0", first_primary), ("tagged", alt)):
        caches = {
            k: sources(jobs, initial, seed, training, k) for k in ("fixed", "recent", "frequency")
        }
        for cache, (hits, at_decode, traffic) in caches.items():
            name2 = name + "_" + cache
            reads = {j.match: j for i, j in enumerate(jobs, 1) if i not in hits}
            if name == "r0":
                ref_misses[cache] = reads
            restored = [{e for k, e in at_decode if k == layer} for layer in range(36)]
            restore = R["by_tier"]()
            repair = R["repair"](cut0 if name == "r0" else cut1, cut0, restored, bases, restore)
            result = {
                "by_phase_tier": traffic,
                "read_change": different(ref_misses[cache], reads),
                "decode_entry_if_restored": {"differences": repair, "loads": R["totals"](restore)},
                "reservations": len(jobs),
                "hits": len(hits),
                "disk": len(reads),
                "clocks": {},
            }
            if cache == "fixed":
                old = history["r0" if name == "r0" else "carry"]["variants"]["bank"]
                for phase in ("prefill", "decode"):
                    value = sum(
                        c["disk_windows"]
                        for ph, tiers in traffic.items()
                        for c in tiers.values()
                        if (ph == "prefill") == (phase == "prefill")
                    )
                    need(value == old[phase]["all"]["disk_jobs"], "historic disk reads")
            for matching in ("same_slot_gen", "same_expert"):
                data = {}
                for label, t in templates.items():
                    by_site, ur, us = priced(
                        jobs, ref, prices[label], exact_slot=matching == "same_slot_gen"
                    )
                    data[label] = inject(t, by_site), exterior[label]
                result["clocks"][matching] = {}
                for g, regs in (("unchanged", data), ("placed", CO["discount"](data, credits))):
                    clocks = {
                        m: CC["assess"](regs, hits, m == "direct") for m in ("copied", "direct")
                    }
                    if name == "r0" and cache in ("recent", "frequency"):
                        before = prev["request"]["full_client_and_decode_ns"][cache][g]
                        need(
                            all(
                                row["with_full_client_cost_ns"] == before[m]
                                for m, row in clocks.items()
                            ),
                            "changed previous control clocks",
                        )
                    result["clocks"][matching][g] = clocks
                    if name == "tagged":
                        clocks["budget"] = unknown_budget(regs, hits, ur)
                result["clocks"][matching]["unpriced"] = {
                    "nonhit_READ": len(ur - hits),
                    "SET": len(us),
                }
            policies[name2] = result
    decisions = {
        p: {
            g: "NO_GO"
            if not row["clocks"]["same_slot_gen"][g]["direct"]["fits_with_grant"]
            else "INCONCLUSIVE"
            for g in ("unchanged", "placed")
        }
        for p, row in policies.items()
    }
    return {
        "schema": "tesy.primary_victims.v1",
        "status": "TRACE_DERIVED",
        "method_sha256": METHOD,
        "source_sha256": SRC["digest"](Path(__file__)),
        "history_sha256": HIST,
        "p63": origin,
        "parent_sha256": DECISION,
        "cold_unique_keys": len(cold),
        "cold_by_phase_and_tier": dict(
            Counter(B["phase"](site[0]) + "_" + IV["by_tier"](k) for k, site in cold.items())
        ),
        "cold_sites_sha256": hashlib.sha256(json.dumps(sorted(cold.items())).encode()).hexdigest(),
        "regardless_of_primary": force,
        "policies": policies,
        "decisions": decisions,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("archive", "placement", "new-output-dir"):
        p.add_argument("--" + arg, type=Path, required=True)
    a = p.parse_args()
    a.new_output_dir.mkdir(mode=0o700)
    try:
        result = run(a)
    except FileNotFoundError as e:
        missing = Path(e.filename).resolve()
        raw = missing.is_relative_to(a.archive.resolve()) or missing.is_relative_to(
            a.placement.resolve()
        )
        result = {"status": "NOT_RUN_RAW_REQUIRED" if raw else "FAIL", "missing": missing.name}
    except (ValueError, KeyError, OSError, AssertionError, TypeError, R["OrderUnknown"]) as e:
        result = {
            "status": "INCONCLUSIVE" if isinstance(e, R["OrderUnknown"]) else "FAIL",
            "reason": str(e),
        }
    tmp = a.new_output_dir / ".pending"
    tmp.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    tmp.rename(a.new_output_dir / "receipt.json")
    print(result["status"], result.get("decisions", result.get("reason", "")))
    raise SystemExit(result["status"] != "TRACE_DERIVED")
