"""Test fixed layer addressing of retained CPU weights on the sealed nominal request."""

import argparse
import gzip
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
G = run_path(HERE.parent / "groups.py")
L = G["L"]
V, F, need, sha = (L[k] for k in ("V", "F", "need", "sha"))
T = V["T"]
METHOD = "ad367e5d8eba21a6587e764cfa1b6a2c627d7b5aca89466c5f68c37a08f32631"
PARENT = "57d3f824e29912dce5d3fdeb8e273775d34c5c8075b798b3d10f03bd88ce2cf5"
PHYSICAL = "ab8cc2eaed4deeedd5c8956d8cb2db428193b072ee1bc9dfd7357e47e1bb9334"
LAYERS = 25
CAP = 252


def digest(rows):
    return hashlib.sha256(L["encode"](rows)).hexdigest()


def quotas(weights):
    """Largest remainders, leaving full layers out of the next allocation."""
    need(len(weights) == LAYERS and all(w > 0 for w in weights), "CPU training weights")
    q = [0] * LAYERS
    open_layers = list(range(LAYERS))
    remaining = CAP
    while remaining:
        weight = sum(weights[i] for i in open_layers)
        full = [i for i in open_layers if remaining * weights[i] >= 88 * weight]
        if full:
            for i in full:
                q[i] = 88
                open_layers.remove(i)
            remaining -= len(full) * 88
            continue
        rem = {}
        for i in open_layers:
            q[i], rem[i] = divmod(remaining * weights[i], weight)
        for i in sorted(open_layers, key=lambda i: (-rem[i], i))[: CAP - sum(q)]:
            q[i] += 1
        break
    need(sum(q) == CAP and max(q) <= 88, "static budget")
    return q


def intervals(w, fx, seed):
    """A secondary slot owns an expert on [capture, release), with the seed at -1."""
    active = {s: (-1, layer, expert) for s, (layer, expert) in enumerate(seed[-CAP:])}
    rows = []
    tx = w["reservations"]
    for i, (r, (tier, src, dst)) in enumerate(zip(tx, fx, strict=True)):
        layer, expert, victim = r[2], r[5], r[6]
        if layer >= LAYERS:
            continue
        need(tier == 0, "wrong tier")
        if src is not None:
            start, owner, key = active.pop(src)
            need((owner, key) == (layer, expert), "promotion lineage")
            rows.append([start, i, layer, expert, src, True])
        if dst is not None:
            if dst in active:
                start, owner, key = active[dst]
                rows.append([start, i, owner, key, dst, False])
            active[dst] = (i, layer, victim)
        need(len(active) <= CAP, "global owner capacity")
    for slot, (start, layer, expert) in active.items():
        rows.append([start, len(tx), layer, expert, slot, False])
    rows.sort()
    need(sum(row[-1] for row in rows) == 469, "promotion count")
    return rows


def fixed_layout(rows, stop, useful):
    """Colour each layer's intervals, with endpoint reuse before the next capture."""
    events = {}
    for start, end, layer, expert, slot, promoted in rows:
        if start >= stop or (useful and not (promoted and end < stop)):
            continue
        key = (layer, expert, slot, start)
        events.setdefault(start, ([], []))[1].append(key)
        events.setdefault(min(end, stop), ([], []))[0].append(key)
    live = [{} for _ in range(LAYERS)]
    peaks, when = [0] * LAYERS, [None] * LAYERS
    assigned = {}
    witness = []
    for step, (ends, starts) in sorted(events.items()):
        for key in ends:
            layer = key[0]
            frame = assigned.pop(key)
            need(live[layer].pop(frame) == key, "wrong static frame at release")
        for key in starts:
            layer = key[0]
            frame = next(f for f in range(89) if f not in live[layer])
            need(frame < 88 and key not in assigned, "identical primaries or bad lineage")
            live[layer][frame] = key
            assigned[key] = frame
            witness.append([*key, frame])
            if len(live[layer]) > peaks[layer]:
                peaks[layer], when[layer] = len(live[layer]), step
    need(not assigned and not any(live), "missing release")
    need(all(r[-1] < peaks[r[0]] for r in witness), "colouring exceeds clique bound")
    return dict(
        frames=sum(peaks),
        capacity=CAP,
        slack=CAP - sum(peaks),
        peaks=peaks,
        peak_at_reservation=when,
        assignments=len(witness),
        assignment_sha256=digest(witness),
        status="GO_CAPACITY" if sum(peaks) <= CAP else "NO_GO_FIXED_LINEAGE",
    ), witness


def layer_policy(w, freq, seed, caps):
    pools = [
        T["Pool"](cap, [k for k in seed if k[0] == layer], freq) for layer, cap in enumerate(caps)
    ]
    content = [{s: e for e, s in p.held.items()} for p in pools]
    primary = {(layer_id, s): (e, g) for layer_id, s, e, g in w["initial"] if layer_id < LAYERS}
    effects = {}
    for i, (_, _, layer, slot, gen, expert, victim) in enumerate(w["reservations"]):
        if layer >= LAYERS:
            continue
        key, old = (layer, expert), (layer, victim)
        need(primary[layer, slot] == (victim, gen - 1), "fixed primary generation")
        p, frames = pools[layer], content[layer]
        src, dst = p.reserve(key, old)
        if src is not None:
            need(frames.pop(src) == key, "fixed promotion content")
        if dst is not None:
            frames[dst] = old
        need(
            frames == {s: k for k, s in p.held.items()} and len(frames) <= caps[layer],
            "fixed layer ownership",
        )
        primary[layer, slot] = (expert, gen)
        effects[i] = (src, dst)
    return effects, [p.peak for p in pools]


def first_consumers(windows, native):
    jobs = native["jobs"]
    index = {tuple(j[0]): i for i, j in enumerate(jobs)}
    barriers = {tuple(site): (start, end, last) for site, start, end, last in native["last"]}
    seen, rows = set(), []
    for site, begin, finish, demands in windows["cpu"]:
        ids = {index[tuple(k)] for k in demands if tuple(k) in index}
        first = ids - seen
        seen.update(first)
        bounds = barriers.get(tuple(site))
        if not bounds:
            continue
        start, end, last = bounds
        pubs = {i: jobs[i][-1] for i in ids}
        peak = max(pubs.values())
        need(
            begin <= start < peak <= end <= finish
            and {i for i, t in pubs.items() if t == peak} == {index[tuple(k)] for k in last},
            "native last required publication",
        )
        rows.append((site, start, pubs, first))
    return rows, seen


def price(waves, jobs, hits):
    amounts = {p: dict(remove_sets=0, remove_read_and_sets=0) for p in L["PHASES"]}
    for site, start, pubs, first in waves:
        changes = first & hits
        if not changes:
            continue
        sets, both = {}, {}
        for i in changes:
            j = jobs[i]
            sets[i] = pubs[i] - sum(j[k + 1] - j[k] for k in (7, 9, 11))
            both[i] = sets[i] - (j[6] - j[5])
            need(j[2] <= both[i] < sets[i] < pubs[i], "native service duration")
        v = amounts[L["phase"](site[0])]
        for kind, changed in (("remove_sets", sets), ("remove_read_and_sets", both)):
            v[kind] += G["contrast"](start, pubs, changed)["group_ns"]
    return amounts


def summarize(tx, effects, baseline, sites):
    hits = {i for i, (s, _) in effects.items() if s is not None}
    phases = {}
    for p in L["PHASES"]:
        rows = {i for i in effects if L["phase"](tx[i][0]) == p}
        used = hits & rows
        captures = sum(effects[i][1] is not None for i in rows)
        misses = len(rows) - len(used)
        phases[p] = dict(
            jobs=len(rows),
            hits=len(used),
            gained=len(used - baseline),
            lost=len((baseline & rows) - hits),
            captures=captures,
            requested_pack_B=misses * F["WINDOW"],
            miss_payload_B=misses * T["PAYLOAD"],
            captured_payload_B=captures * T["PAYLOAD"],
        )
    site_hits = {
        key: [j["expert"] for j in case["jobs"] if j["index"] in hits]
        for key, case in sites.items()
    }
    return dict(
        phases=phases,
        sites=site_hits,
        hit_indexes=sorted(hits),
        effects_sha256=digest(sorted(effects.items())),
    )


def evaluate():
    need(sha(HERE / "address-protocol.md") == METHOD, "registered method")
    previous = F["SRC"]["pinned"](
        HERE.parent / "evidence-groups-20261128-r01/decision.json", PARENT
    )
    cases = F["SRC"]["pinned"](HERE / "evidence-20261128-r01/scenarios.json", PHYSICAL)
    history = HERE.parent / "evidence-lifetime-20261128-r01"
    need(
        sha(history / "waves.json.gz")
        == F["SRC"]["pinned"](history / "decision.json", G["PRIOR"])["compressed_windows_sha256"],
        "consumer windows",
    )
    tx, fx = V["sources"]()
    w = F["unpack"](V["TIER"] / "evidence-tier-20261128-r01/transactions.json.gz")
    freq = Counter({(layer_id, e): n for layer_id, e, n in w["counts"]})
    primary = {(layer_id, e) for layer_id, s, e, g in w["initial"]}
    seed = [
        (layer_id, e)
        for layer_id, e in w["seed"]
        if layer_id < LAYERS and (layer_id, e) not in primary
    ]
    need(len(seed) == len(set(seed)) == 227, "causal entry")
    global_effect = {i: (src, dst) for i, (tier, src, dst) in enumerate(fx) if tier == 0}
    base = {i for i, (src, _) in global_effect.items() if src is not None}
    prefix = next(i for i, row in enumerate(tx) if row[0] > 46)
    need(all(row[0] > 46 for row in tx[prefix:]), "prefix endpoint")
    rows = intervals(w, fx, seed)
    witness = {"original_intervals": rows}
    limits = {}
    for label, stop in (("to_first", prefix), ("complete", len(tx))):
        limits[label] = {}
        for mode in ("all", "useful"):
            limits[label][mode], witness[label + "_" + mode] = fixed_layout(
                rows, stop, mode == "useful"
            )
    trained = [
        sum(v for (layer_id, _), v in freq.items() if layer_id == layer) for layer in range(LAYERS)
    ]
    sites = cases["P97"]
    for k in sites:
        need(
            [(j["index"], j["expert"]) for j in sites[k]["jobs"]]
            == [(j["index"], j["expert"]) for j in cases["P106"][k]["jobs"]],
            "registered site",
        )
    arms = {"global": summarize(tx, global_effect, base, sites)}
    for name, weights in (("equal", [1] * LAYERS), ("T1", trained)):
        caps = quotas(weights)
        effect, peaks = layer_policy(w, freq, seed, caps)
        arms[name] = dict(**summarize(tx, effect, base, sites), quota=caps, peaks=peaks)
    for k in sites:
        need(
            arms["global"]["sites"][k] == [j["expert"] for j in sites[k]["jobs"] if j["hit"]],
            "physical control eligibility",
        )
    windows = F["unpack"](history / "waves.json.gz")
    service = L["X"]["ORIGINAL"] / "service.json.gz"
    need(sha(service) == V["SERVICE"], "producer clocks")
    service = F["unpack"](service)
    for tag, native in service.items():
        waves, consumed = first_consumers(windows[tag], native)
        for name, arm in arms.items():
            hits = set(arm["hit_indexes"])
            credits = price(waves, native["jobs"], hits)
            if name == "global":
                for p, values in credits.items():
                    for kind, value in values.items():
                        old = previous["phases"][tag][p]
                        need(
                            value == sum(v[kind]["group_ns"] for v in old.values()),
                            "original per-wave credit",
                        )
            arm.setdefault("journals", {})[tag] = dict(
                phases=credits,
                unconsumed=sorted(hits - consumed),
                to_first={k: sum(credits[p][k] for p in L["PHASES"][:3]) for k in credits["tail"]},
            )
    for name, arm in arms.items():
        first_hits = sum(i < prefix for i in arm["hit_indexes"])
        arm["to_first_hits"] = first_hits
        if name != "global":
            ctrl = arms["global"]
            gates = dict(
                decode_group=arm["sites"]["decode4"] == ctrl["sites"]["decode4"],
                first_hits=first_hits >= sum(i < prefix for i in base),
            )
            for tag in windows:
                kind = "remove_read_and_sets"
                gates[tag] = (
                    arm["journals"][tag]["to_first"][kind]
                    >= ctrl["journals"][tag]["to_first"][kind]
                )
            arm.update(
                gates=gates,
                status="GO_FIXED_INTEGRATION_FIXTURE"
                if all(gates.values())
                else "NO_GO_FIXED_POLICY",
            )
    return dict(
        evidence="FORMAL_AND_TRACE_DERIVED_FIXED_CLOCKS",
        limits=limits,
        policies=arms,
        training_CPU_reservations=trained,
        registered_cpu_slots=CAP,
        source_sha256=sha(Path(__file__)),
        protocol_sha256=METHOD,
        parents=[PARENT, PHYSICAL, V["SERVICE"]],
        product_gain_ns=None,
        model_forwards=0,
        HTTP_requests=0,
    ), witness


def main():
    p = argparse.ArgumentParser(description=__doc__)
    dest = p.add_mutually_exclusive_group(required=True)
    dest.add_argument("--check", type=Path)
    dest.add_argument("--new-output-dir", type=Path)
    a = p.parse_args()
    os.umask(0o077)
    out = a.new_output_dir
    if out:
        out.mkdir()
    try:
        decision, witness = evaluate()
        raw = L["encode"](witness)
        decision["witness_sha256"] = hashlib.sha256(raw).hexdigest()
        if out:
            (out / "assignments.json.gz").write_bytes(gzip.compress(raw, mtime=0))
            tmp = out / ".pending"
            tmp.write_text(json.dumps(decision, sort_keys=True, indent=2) + "\n")
            tmp.rename(out / "decision.json")
        else:
            need(
                raw == gzip.decompress((a.check / "assignments.json.gz").read_bytes())
                and decision == json.loads((a.check / "decision.json").read_bytes()),
                "published capacity and credit",
            )
        print({k: r.get("status", "CONTROL") for k, r in decision["policies"].items()})
    except Exception as exc:
        if out:
            (out / "FAIL.json").write_text(json.dumps(dict(error=repr(exc))) + "\n")
        raise


if __name__ == "__main__":
    main()
