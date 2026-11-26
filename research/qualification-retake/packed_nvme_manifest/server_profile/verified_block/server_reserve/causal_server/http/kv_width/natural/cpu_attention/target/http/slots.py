"""Match native packed rereads to retired generations of the same 40-slot pool."""

import argparse
import hashlib
import os
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
B = run_path(str(HERE / "reloads.py"))
C, G, R, need, sha, save = (B[k] for k in ("C", "G", "R", "need", "sha", "save"))
METHOD = "55f7e168d3e14c19e0304804b1c5318f9096e5c83bb04a0d365744dedb974a15"
PREVIOUS = "32f91f7a2a5922e558e597e60589f176d3951c981cd49bf83580bba7b59433ae"


@dataclass
class Wave:
    site: tuple
    reservations: list = field(default_factory=list)
    demands: list = field(default_factory=list)
    readers: dict = field(default_factory=dict)


@dataclass
class Epoch:
    begin: int
    end: int
    last_reader: int = -1
    first_demand: int | None = None


def content_hash(slots):
    digest = hashlib.sha256()
    for (layer, slot), (_, _, generation, expert) in sorted(slots.items()):
        digest.update(struct.pack("<5q", layer, slot, expert, generation, 2))
    return digest.hexdigest()


def gather(rows):
    native = C["NATIVE"]["host_trace"](rows)
    current, initial, waves, parking = {}, {}, [], {}
    for r in rows:
        if r.kind == 1 and r.call == 3:
            break
        if r.kind == 1 and r.call == 2:
            initial = current.copy()
        if r.kind == 9 and r.call == 2:
            waves.append(Wave(C["origin"](r)))
        if r.kind in (5, 11):
            key = C["key"](r)
            loc = (r.layer, r.slot)
            if r.kind == 11:
                old = current[loc]
                need((old[2] + 1, old[3]) == (r.gen, r.a), "physical generation")
                if r.call == 2:
                    waves[-1].reservations.append((old, key))
            current[loc] = key
        if r.kind == 10 and r.call == 2:
            key = C["key"](r)
            need(current[key[:2]] == key, "native demand")
            waves[-1].demands.append(key)
        if r.kind == 23 and r.call == 2:
            wave = waves[-1]
            need(wave.site == C["origin"](r), "remap site")
            slots = [key[1] for key in wave.demands]
            if r.wave >= 0:
                # The pin uses the current ordered demands then borrows enough old
                # parking slots to reach four. Protect every possible masked operand.
                if len(slots) >= 4:
                    parking[r.layer] = slots
                elif r.layer in parking:
                    slots = slots + parking[r.layer][: 4 - len(slots)]
                    parking[r.layer] = slots
                else:
                    slots = list(range(40))
            need(len(set(slots)) == len(slots), "distinct protected physical readers")
            wave.readers = {s: current[r.layer, s] for s in slots}
    need(len(initial) == len(current) == 1440, "complete endpoints")
    need(content_hash(current) == native["first_decode"]["sha256"], "independent decode snapshot")
    return initial, waves, current


def lifetimes(initial, waves):
    limit = len(waves)
    epochs = {key: Epoch(-1, limit) for key in initial.values()}
    uses = defaultdict(list)
    for i, wave in enumerate(waves):
        for old, new in wave.reservations:
            need(epochs[old].end == limit and new not in epochs, "unique epoch")
            epochs[old].end = i
            epochs[new] = Epoch(i, limit)
        for key in wave.readers.values():
            epochs[key].last_reader = i
        for key in wave.demands:
            if epochs[key].first_demand is None:
                epochs[key].first_demand = i
                uses[C["expert"](key)].append(key)
    return epochs, uses


def borrowers(waves, epochs, uses):
    sources = {}
    for history in uses.values():
        first_tile = waves[epochs[history[0]].first_demand].site[1]
        for earlier, new in zip(history, history[1:], strict=False):
            old, dest = epochs[earlier], epochs[new]
            if first_tile < waves[dest.first_demand].site[1]:
                need(old.first_demand < old.end <= dest.begin <= dest.first_demand, "reread order")
                sources[new] = earlier
    retired = defaultdict(list)
    protected = set(sources.values())
    for key, span in epochs.items():
        if key not in protected and span.end < len(waves):
            retired[key[0]].append(key)
    edges = {}
    for new, old in sorted(sources.items()):
        start, finish = epochs[old].end, epochs[new].begin
        edges[new] = [
            carrier
            for carrier in sorted(retired[new[0]])
            if start < finish
            and carrier[1] not in (old[1], new[1])
            and max(epochs[carrier].begin, epochs[carrier].last_reader) < start
            and epochs[carrier].end > finish
        ]
    return sources, edges


def matching(edges):
    owners = {}

    def augment(left, seen):
        for carrier in edges[left]:
            if carrier in seen:
                continue
            seen.add(carrier)
            if carrier not in owners or augment(owners[carrier], seen):
                owners[carrier] = left
                return True
        return False

    for left in sorted(edges):
        augment(left, set())
    chosen = {left: carrier for carrier, left in owners.items()}
    # A vertex cover of equal size independently certifies this maximum.
    reached = set(edges) - chosen.keys()
    stack = sorted(reached)
    right = set()
    while stack:
        left = stack.pop()
        for carrier in edges[left]:
            if carrier != chosen.get(left) and carrier not in right:
                right.add(carrier)
                if carrier in owners and owners[carrier] not in reached:
                    reached.add(owners[carrier])
                    stack.append(owners[carrier])
    cover = set(edges) - reached
    need(all(k in cover or set(v) <= right for k, v in edges.items()), "vertex cover")
    need(len(cover) + len(right) == len(chosen), "maximum certificate")
    return chosen, dict(left=sorted(cover), right=sorted(right))


def play(initial, waves, final, schedule):
    logical = initial.copy()
    payload = {loc: key[3] for loc, key in initial.items()}
    saves, copies = defaultdict(list), {}
    for at, old, dest, carrier in schedule:
        saves[at].append((old, carrier))
        need(dest not in copies, "duplicate substitution")
        copies[dest] = carrier
    counts = Counter()
    for i, wave in enumerate(waves):
        for source, carrier in saves[i]:
            need(logical[source[:2]] == source and logical[carrier[:2]] == carrier, "save lineage")
            need(payload[source[:2]] == source[3], "source bytes changed")
            payload[carrier[:2]] = payload[source[:2]]
            counts["saves"] += 1
        for old, new in wave.reservations:
            loc = new[:2]
            need(logical[loc] == old, "original assignment")
            if new in copies:
                carrier = copies[new]
                need(logical[carrier[:2]] == carrier, "carrier overwritten")
                expert = payload[carrier[:2]]
                counts["restores"] += 1
            else:
                expert = new[3]
                counts["disk"] += 1
            need(expert == new[3], "wrong expert at publication")
            logical[loc], payload[loc] = new, expert
        for key in wave.readers.values():
            need(logical[key[:2]] == key and payload[key[:2]] == key[3], "changed graph operand")
            counts["protected_wave_slots"] += 1
    need(logical == final and all(payload[k] == v[3] for k, v in final.items()), "decode entry")
    need(counts["saves"] == counts["restores"] == len(schedule), "copy conservation")
    return dict(counts)


def fixture():
    graph = {1: [4, 5], 2: [4], 3: [4]}
    chosen, cover = matching(graph)
    need(len(chosen) == 2 and chosen[1] == 5 and len(cover["right"]) == 1, "augment and certify")
    a, b, c = (0, 0, 1, 7), (0, 1, 1, 5), (0, 2, 1, 6)
    x, y, z = (0, 0, 2, 9), (0, 2, 2, 7), (0, 1, 2, 10)
    start = {k[:2]: k for k in [a, b, c]}
    end = {k[:2]: k for k in [x, z, y]}
    waves = [Wave((2, i, 0, 0)) for i in range(1, 5)]
    waves[0].demands, waves[0].readers = [a], {0: a}
    for wave, old, new in zip(waves[1:], [a, c, b], [x, y, z], strict=True):
        wave.reservations = [(old, new)]
        wave.demands, wave.readers = [new], {new[1]: new}
    epochs, uses = lifetimes(start, waves)
    sources, edges = borrowers(waves, epochs, uses)
    need(sources == {y: a} and edges == {y: [b]}, "one available physical carrier")
    schedule = [(1, a, y, b)]
    need(play(start, waves, end, schedule)["disk"] == 2, "one avoided read")
    waves[2].readers[1] = b
    epochs, uses = lifetimes(start, waves)
    need(not borrowers(waves, epochs, uses)[1][y], "parking excludes carrier")
    try:
        play(start, waves, end, schedule)
    except ValueError:
        return ["augmenting_path", "minimum_cover", "byte_lineage", "parking_rejects"]
    raise ValueError("missed changed parking bytes")


def arm(rows, previous):
    initial, waves, final = gather(rows)
    epochs, uses = lifetimes(initial, waves)
    sources, edges = borrowers(waves, epochs, uses)
    expected = previous["population"]["total"]["reloads"]
    need(len(edges) == expected, "part 188 candidate population")
    chosen, cover = matching(edges)
    schedule = [(epochs[sources[d]].end, sources[d], d, k) for d, k in sorted(chosen.items())]
    control, candidate = (play(initial, waves, final, s) for s in ([], schedule))
    need(control["disk"] - candidate["disk"] == len(chosen), "identical supplied work")
    table = Counter(
        ("CPU" if k[0] < 25 else "CUDA0", waves[epochs[k].begin].site[1]) for k in chosen
    )
    witness = [
        dict(
            save=waves[i].site,
            load=waves[epochs[new].begin].site,
            source=old,
            target=new,
            carrier=carrier,
        )
        for i, old, new, carrier in schedule
    ]
    return dict(
        waves=len(waves),
        candidates=len(edges),
        edges=sum(map(len, edges.values())),
        candidates_with_carrier=sum(bool(v) for v in edges.values()),
        count=len(chosen),
        by_tier_tile=[dict(tier=t, tile=i, saved=n) for (t, i), n in sorted(table.items())],
        initial_sha256=content_hash(initial),
        decode_sha256=content_hash(final),
        control=control,
        candidate=candidate,
        schedule=witness,
        minimum_vertex_cover=cover,
    )


def run(a):
    head, tree = G["tree"](G["REPO"])
    need(head == a.commit and sha(HERE / "slots-protocol.md") == METHOD, "frozen design")
    previous = G["read"](a.previous / "result.json", PREVIOUS)
    controls = fixture()
    data, steps = R["cases"](a)
    tiers, result = None, None
    for label in ("P106", "P97"):
        rows, tiers, ids = B["trace_arm"](a, label, tiers, data, steps)
        need(
            B["account"](rows, tiers) == previous["population"]
            and ids == previous["target_id_digests"],
            "ancestry",
        )
        observed = arm(rows, previous)
        if result is not None:
            need(observed == result, "independent schedule, slots and certificate")
        result = observed
    n = result["count"]
    credit = n * B["WINDOW"]
    pricing = {}
    for name, old in previous["projected"].items():
        deficits = dict(free=old["zero_unknown_deficit_bytes"])
        if "at_six_deficit_bytes" in old:
            deficits["at_six"] = old["at_six_deficit_bytes"]
        pricing[name] = {
            k: dict(
                required=v,
                signed_margin_bytes=credit - v,
                signed_time_budget_s=(credit - v) / B["IO"]["RATE"],
            )
            for k, v in deficits.items()
        }
    return dict(
        status="TRACE_DERIVED_MAXIMUM_UNDER_RETIRED_SLOT_RULE",
        commit=head,
        tree=tree,
        protocol_sha256=METHOD,
        prior_sha256=PREVIOUS,
        fixture=controls,
        arms=["P106", "P97"],
        matched=result,
        aligned_reads_avoided_bytes=credit,
        two_physical_copies_payload_bytes=2 * n * B["PAYLOAD"],
        pricing=pricing,
        model_starts=0,
        http_requests=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("archive", "previous", "capture", "verified", "plan", "new-output-dir"):
        p.add_argument("--" + k, required=True, type=Path)
    p.add_argument("--commit", required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.new_output_dir.mkdir()
    try:
        result = run(a)
    except Exception as exc:
        result = dict(
            status="FAIL_PRESERVED",
            error=f"{type(exc).__name__}: {exc}",
            commit=a.commit,
            protocol_sha256=METHOD,
        )
    save(a.new_output_dir / "result.json", result)
    print(result["status"], result.get("error", ""))
    raise SystemExit(result["status"] == "FAIL_PRESERVED")
